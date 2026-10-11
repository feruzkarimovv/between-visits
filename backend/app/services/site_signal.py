"""Site Signal read service (task B17): the committed study and the site 101 live bridge.

Contract: docs/03 §5.1-5.3 (payloads), §6.1 (roles); shapes: docs/02 § Site Signal (models in app/schemas.py);
statistics: docs/11, which wins on any statistical detail.

Committed study
---------------
Reads what `make site-signal` wrote to MONITORING_OUT (`signal_run.json`, `episodes.json`, `site_ae.json`,
`thresholds.json`, `answer_key.json`, `equity.json`) and the validation summary at SITE_SIGNAL_SUMMARY. Each file
version is parsed once: the caches are `lru_cache`s keyed by path, mtime and size, so a rewritten file is read
again on the next request. Every file is validated against its Pydantic model, and the study files are checked
against each other (one row per site, episodes at known sites, matched AE rows that exist for the same subject,
thresholds from the same run). Any load, parse or schema error raises 503 `site_signal_unavailable` (REQ-025):
the UI then renders every site grey "not computed", never green.

This module serves numbers; it does not make them. Tiers, thresholds (`thresholds.json`, REQ-023) and the
answer-key confusion counts (`answer_key.json`) come from `monitoring/`. The only tallies made here are the
descriptive language and pace strata of one site's simulated O/E-set episodes and, through
`episodes.paged_stratum()`, its paged stratum.

Site 101 live bridge
--------------------
MEASURED episodes are built at request time from the app database: every check-in of the study whose
`Study.site_id` is the requested site, graded by the docs/11 §4.2 mapping (`term_grade`), paged by the
highest escalation level of the call, built and classified by `episodes.py` with the request's DISPLAY_TZ local
date as the data cut (docs/11 §6.1). They are listed first in the drill-down and never enter `signal`, `strata`
or `paged_stratum`, and never pool with simulated episodes (docs/11 §2.4, §15 rule 2). The live bridge is
integrated by construction (its coordinator reviews drafts), so once its entry window has passed an episode is
`not_evaluated` (docs/11 §6.4 with the `integrated_mode` guard of §2.4), never matched or unmatched.

No LLM is imported on this path (REQ-021), there is no numpy or scipy, and there is no numeric literal other
than 0, 1 and -1 (REQ-023): every constant comes from data/signal_rules.json, the output files or the
standard library.
"""

import json
import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from http import HTTPStatus
from pathlib import Path
from typing import Any, get_args

from pydantic import TypeAdapter
from sqlmodel import Session, select

from app import content
from app.config import get_settings
from app.errors import ApiError
from app.models import Answer, CheckIn, DraftEntry, Escalation, Patient, Study
from app.schemas import (
    COMMITTED_RUN_ID,
    AnswerKeyFile,
    AnswerKeyOut,
    EpisodeEvidence,
    EpisodeStatus,
    EquityOut,
    Funnel,
    PagedStratum,
    RunThresholds,
    SignalLabels,
    SignalRunFile,
    SignalRunMeta,
    SiteAERow,
    SiteCard,
    SiteDetailOut,
    SiteEpisode,
    SiteFile,
    SiteRowOut,
    SiteSignalRow,
    SiteSignalValidationOut,
    SitesOut,
    SiteStrata,
    StratumCount,
    SubjectLanguage,
    SubjectPace,
    ThresholdsFile,
)
from app.services import episodes, rules
from app.services.clinical import answers_map, baseline_of
from app.timeutil import local_date, utcnow

log = logging.getLogger("bv.site_signal")

SIGNAL_RUN = "signal_run.json"
EPISODES = "episodes.json"
SITE_AE = "site_ae.json"
THRESHOLDS = "thresholds.json"
ANSWER_KEY = "answer_key.json"
EQUITY = "equity.json"
STUDY_FILES: tuple[tuple[str, Any], ...] = (
    (SIGNAL_RUN, SignalRunFile),
    (EPISODES, list[SiteEpisode]),
    (SITE_AE, list[SiteAERow]),
    (THRESHOLDS, ThresholdsFile),
)

SIMULATED, MEASURED, MIXED = "SIMULATED", "MEASURED", "MIXED"
SYNTHETIC, LIVE_CALL, REPLAY = "synthetic", "live_call", "replay"
NOT_COMPUTED = "not_computed"
COMPLETED = "completed"
NO_ESCALATION = "none"
ENGLISH = "en"
EPISODE_STATUSES = frozenset(get_args(EpisodeStatus))
# An item answered `unknown` or `not_measured` counts as not answered (docs/11 §4.2).
NOT_ANSWERED = frozenset(rules.NON_VALUES - {None})

Stamp = tuple[int, int]  # (mtime_ns, size) of one file version


class SiteSignalUnavailable(ApiError):
    """503 `site_signal_unavailable` (docs/03 §5.6): the UI shows every site grey, never green."""

    def __init__(self, what: str) -> None:
        super().__init__(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "site_signal_unavailable",
            f"Site Signal data could not be loaded ({what}); every site is shown as not computed.",
        )


def _guard[T](what: str, build: Callable[[], T]) -> T:
    """Run `build`; any error other than an ApiError becomes 503 `site_signal_unavailable`, logged once."""
    try:
        return build()
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001  REQ-025: any load or schema error is a 503, never a partial answer
        log.warning("site_signal_unavailable what=%s error=%s reason=%s", what, type(exc).__name__,
                    " ".join(str(exc).split()))
        raise SiteSignalUnavailable(what) from exc


# ---- file loading: lru_cache keyed by path and file version --------------------------------------------------

_seen: dict[Path, Stamp] = {}


def _stamp(path: Path) -> Stamp:
    """The file's version (FileNotFoundError when missing). A new version drops every cached parse, so the caches
    hold one version per file."""
    st = path.stat()
    stamp = (st.st_mtime_ns, st.st_size)
    if _seen.setdefault(path, stamp) != stamp:
        _seen[path] = stamp
        _document.cache_clear()
        _study.cache_clear()
    return stamp


@lru_cache
def _document(path: Path, stamp: Stamp, shape: Any) -> Any:
    """One file version parsed and validated against `shape` (a model or list of models)."""
    return TypeAdapter(shape).validate_python(json.loads(path.read_text(encoding="utf-8")))


def _load(path: Path, shape: Any) -> Any:
    return _document(path, _stamp(path), shape)


def clear_cache() -> None:
    """Forget every parsed file (tests; a changed MONITORING_OUT is picked up without it)."""
    _seen.clear()
    _document.cache_clear()
    _study.cache_clear()


# ---- committed study -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CommittedStudy:
    """The committed run `sr_committed`, validated and cross-checked. `episodes` lists each site's simulated
    episodes in file order (every site has an entry)."""

    run: SignalRunMeta
    sites: dict[str, SiteFile]
    rows: dict[str, SiteSignalRow]
    funnel: Funnel
    episodes: dict[str, list[SiteEpisode]]


def _by_id[T](items: Iterable[T], key: Callable[[T], str], what: str) -> dict[str, T]:
    out: dict[str, T] = {}
    for item in items:
        k = key(item)
        if k in out:
            raise ValueError(f"duplicate {what} {k!r}")
        out[k] = item
    return out


def _assemble(
    run_file: SignalRunFile, simulated: list[SiteEpisode], site_aes: list[SiteAERow], thresholds: ThresholdsFile
) -> CommittedStudy:
    run = run_file.run
    if (thresholds.sap_tag_commit, thresholds.eval_seed) != (run.sap_tag_commit, run.eval_seed):
        raise ValueError(f"{THRESHOLDS} and {SIGNAL_RUN} come from different runs")
    served = RunThresholds(discordance=thresholds.discordance, rate_kri=thresholds.rate_kri,
                           simaerep_classic=thresholds.simaerep_classic)
    if run.thresholds is not None and run.thresholds != served:
        raise ValueError(f"run.thresholds in {SIGNAL_RUN} differ from {THRESHOLDS}")
    expected = thresholds.expected_false_look_flags_per_study
    if run.expected_false_look_flags_per_study not in (None, expected):
        raise ValueError(f"expected_false_look_flags_per_study in {SIGNAL_RUN} differs from {THRESHOLDS}")
    meta = SignalRunMeta.model_validate(
        {**run.model_dump(), "thresholds": served.model_dump(), "expected_false_look_flags_per_study": expected}
    )

    sites = _by_id(run_file.sites, lambda s: s.site_id, "site")
    rows = _by_id(run_file.rows, lambda r: r.site_id, "signal row")
    if rows.keys() != sites.keys():
        raise ValueError(f"{SIGNAL_RUN}: sites and rows list different sites")
    study_reason = run.study_not_computed_reason
    if study_reason is not None and any(r.not_computed_reason != study_reason for r in rows.values()):
        raise ValueError(f"{SIGNAL_RUN}: study not computed ({study_reason}) but a row has another reason")

    aes = _by_id(site_aes, lambda a: a.site_ae_id, "site AE row")
    by_site: dict[str, list[SiteEpisode]] = {site_id: [] for site_id in sites}
    _by_id(simulated, lambda e: e.episode_id, "episode")
    for ep in simulated:
        if ep.site_id not in by_site:
            raise ValueError(f"episode {ep.episode_id} is at unknown site {ep.site_id!r}")
        if ep.data_origin != SIMULATED or ep.evidence.source != SYNTHETIC:
            raise ValueError(f"episode {ep.episode_id}: a simulated episode is SIMULATED with a synthetic quote")
        if ep.matched_site_ae_id is not None:
            ae = aes.get(ep.matched_site_ae_id)
            if ae is None or (ae.site_id, ae.subject_id) != (ep.site_id, ep.subject_id):
                raise ValueError(f"episode {ep.episode_id}: matched AE row {ep.matched_site_ae_id} not in {SITE_AE}")
        by_site[ep.site_id].append(ep)
    return CommittedStudy(run=meta, sites=sites, rows=rows, funnel=run_file.funnel, episodes=by_site)


@lru_cache
def _study(paths: tuple[Path, ...], stamps: tuple[Stamp, ...]) -> CommittedStudy:
    run_file, simulated, site_aes, thresholds = (
        _document(path, stamp, shape) for path, stamp, (_, shape) in zip(paths, stamps, STUDY_FILES, strict=True)
    )
    return _assemble(run_file, simulated, site_aes, thresholds)


def committed_study() -> CommittedStudy:
    """The committed study from MONITORING_OUT, or 503 `site_signal_unavailable`."""

    def build() -> CommittedStudy:
        out = get_settings().monitoring_out
        paths = tuple(out / name for name, _ in STUDY_FILES)
        return _study(paths, tuple(_stamp(path) for path in paths))

    return _guard("committed study", build)


# ---- labels ------------------------------------------------------------------------------------------------


def _flatten(node: Any) -> Any:
    """`{"en": "..."}` leaves become their English string; other dicts are flattened key by key."""
    if isinstance(node, Mapping):
        if ENGLISH in node and all(isinstance(v, str) for v in node.values()):
            return node[ENGLISH]
        return {key: _flatten(value) for key, value in node.items()}
    return node


def signal_labels() -> SignalLabels:
    """`data/signal_rules.json` `labels`, `en` strings flattened (docs/03 §5.1); the UI has no label literals."""
    return _guard("labels", lambda: SignalLabels.model_validate(_flatten(content.signal_rules()["labels"])))


# ---- GET /api/sites --------------------------------------------------------------------------------------


def sites_overview() -> SitesOut:
    """`GET /api/sites`: run metadata with the thresholds from thresholds.json, labels, funnel and one row per
    site. Computed sites first by `rank`, then not-computed sites by `site_id`."""
    study = committed_study()
    labels = signal_labels()
    open_queries: dict[str, int] = {}  # sent or answered site queries per site: the SiteQuery table lands in B18
    rows = list(study.rows.values())
    computed = sorted((r for r in rows if r.tier != NOT_COMPUTED), key=lambda r: (r.rank, r.site_id))
    not_computed = sorted((r for r in rows if r.tier == NOT_COMPUTED), key=lambda r: r.site_id)
    sites = [
        SiteRowOut.model_validate(
            {**study.sites[r.site_id].model_dump(), **r.model_dump(), "open_queries": open_queries.get(r.site_id, 0)}
        )
        for r in [*computed, *not_computed]
    ]
    return SitesOut(run=study.run, labels=labels, funnel=study.funnel, sites=sites)


# ---- GET /api/sites/{site_id} ----------------------------------------------------------------------------


def parse_statuses(raw: str | None) -> frozenset[str] | None:
    """`?status=unmatched,pending` -> the set of statuses, None for no filter; 422 for an unknown status."""
    if raw is None:
        return None
    wanted = frozenset(part.strip() for part in raw.split(",") if part.strip())
    unknown = sorted(wanted - EPISODE_STATUSES)
    if unknown:
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error",
                       f"unknown episode status {', '.join(unknown)}; use {', '.join(episodes.STATUSES)}")
    return wanted or None


def _strata(simulated: Sequence[SiteEpisode]) -> SiteStrata:
    """Descriptive counts of the O/E set (evaluable, not paged: matched or unmatched) by language and pace."""
    oe = [ep for ep in simulated if ep.status in episodes.OE_STATUSES]

    def tally(values: tuple[str, ...], of: Callable[[SiteEpisode], str]) -> dict[str, StratumCount]:
        return {
            value: StratumCount(evaluable=sum(of(ep) == value for ep in oe),
                                matched=sum(of(ep) == value and ep.status == episodes.MATCHED for ep in oe))
            for value in values
        }

    return SiteStrata(language=tally(get_args(SubjectLanguage), lambda ep: ep.language),
                      pace=tally(get_args(SubjectPace), lambda ep: ep.pace))


def site_detail(
    session: Session, site_id: str, *, run_id: str = COMMITTED_RUN_ID, statuses: frozenset[str] | None = None
) -> SiteDetailOut:
    """`GET /api/sites/{site_id}`: card, signal row, episodes (MEASURED live episodes first), strata, paged
    stratum and queries. `statuses` filters the listed episodes only; strata and the paged stratum always describe
    the site's simulated episodes."""
    if run_id != COMMITTED_RUN_ID:  # blind runs (SignalRun rows) land in B19
        raise ApiError(HTTPStatus.NOT_FOUND, "signal_run_not_found", f"signal run {run_id} not found")
    study = committed_study()
    site = study.sites.get(site_id)
    if site is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "site_not_found", f"site {site_id} is not in run {run_id}")
    simulated = study.episodes[site_id]
    live = _guard("live episodes", lambda: live_episodes(session, site_id))
    card = SiteCard.model_validate({**site.model_dump(), "data_origin": MIXED if live else site.data_origin})
    listed = [ep for ep in (*live, *simulated) if statuses is None or ep.status in statuses]
    paged = episodes.paged_stratum(ep.model_dump() for ep in simulated)
    return SiteDetailOut(site=card, signal=study.rows[site_id], episodes=listed, strata=_strata(simulated),
                         paged_stratum=PagedStratum(**paged), queries=[])


# ---- site 101 live bridge (MEASURED) ---------------------------------------------------------------------


def data_cut_today() -> date:
    """The live bridge's data cut: the request's DISPLAY_TZ local date (docs/11 §6.1)."""
    return local_date(utcnow())


def _answered(answer: rules.AnswerInput) -> bool:
    return answer.option_code not in NOT_ANSWERED and (answer.option_code is not None or answer.numeric_value is not None)


def term_grade(term: str, answers: rules.Answers, baseline: Mapping[str, Any] | None) -> int | None:
    """g_k of docs/11 §4.2 for one completed call: None when the term was not asked (no item answered, or only
    `unknown` / `not_measured`); 0 when `rules.term_present` is false (reported absent); else
    `rules.grade(...).provisional_grade`, which is None when the grade basis is `needs_clinician`."""
    asked = [answers[code] for code in content.items_for_term(term) if code in answers]
    if not any(_answered(a) for a in asked):
        return None
    if not rules.term_present(term, answers):
        return 0
    return rules.grade(term, answers, dict(baseline) if baseline is not None else None).provisional_grade


def _call_time(checkin: CheckIn) -> datetime:
    """When the call happened: its start, else its end, schedule or creation time (always set)."""
    return checkin.started_at or checkin.ended_at or checkin.scheduled_for or checkin.created_at


def _translations(session: Session, checkin_ids: Iterable[str]) -> dict[str, dict[str, tuple[str | None, float | None]]]:
    """Stored AI translations (and times) of quotes on these check-ins, from draft evidence: no LLM call here."""
    out: dict[str, dict[str, tuple[str | None, float | None]]] = {}
    ids = sorted(set(checkin_ids))
    if not ids:
        return out
    for draft in session.exec(select(DraftEntry).where(DraftEntry.checkin_id.in_(ids))).all():  # type: ignore[attr-defined]
        per_call = out.setdefault(draft.checkin_id, {})
        for ev in draft.evidence or []:
            quote = ev.get("quote")
            if quote and (quote not in per_call or per_call[quote][0] is None):
                per_call[quote] = (ev.get("translation_en"), ev.get("t_s"))
    return out


def _evidence(
    checkin: CheckIn, term: str, answers: Sequence[Answer], translations: Mapping[str, tuple[str | None, float | None]]
) -> EpisodeEvidence:
    """The verbatim quote of the episode's first call: the latest quoted answer of the term that reports the
    symptom, else the latest quoted answer of the term."""
    items = set(content.items_for_term(term))
    quoted = [a for a in answers if a.item_code in items and a.verbatim_quote.strip()]
    reporting = [a for a in quoted if rules.term_present(term, answers_map([a]))]
    source = REPLAY if checkin.channel == REPLAY else LIVE_CALL
    if not quoted:
        return EpisodeEvidence(quote="", quote_lang=checkin.language, translation_en=None, translation_is_ai=False,
                               t_s=None, source=source, checkin_id=checkin.id)
    pick = (reporting or quoted)[-1]
    translation, t_s = translations.get(pick.verbatim_quote, (None, None))
    if pick.quote_lang == ENGLISH:
        translation = None
    return EpisodeEvidence(quote=pick.verbatim_quote, quote_lang=pick.quote_lang, translation_en=translation,
                           translation_is_ai=translation is not None,
                           t_s=pick.t_s if pick.t_s is not None else t_s, source=source, checkin_id=checkin.id)


def live_episodes(session: Session, site_id: str) -> list[SiteEpisode]:
    """MEASURED episodes of the live site, newest first; [] for any other site. Built from every check-in of the
    study (only completed calls contribute, docs/11 §6.3) by `episodes.build_episodes` and `episodes.classify`."""
    study_ids = list(session.exec(select(Study.id).where(Study.site_id == site_id)).all())
    if not study_ids:
        return []
    patients = {p.id: p for p in session.exec(select(Patient).where(Patient.study_id.in_(study_ids))).all()}  # type: ignore[attr-defined]
    if not patients:
        return []
    checkins = sorted(
        session.exec(select(CheckIn).where(CheckIn.patient_id.in_(list(patients)))).all(),  # type: ignore[attr-defined]
        key=lambda c: (_call_time(c), c.id),
    )
    by_id = {c.id: c for c in checkins}
    completed = [c.id for c in checkins if c.status == COMPLETED]
    answers: dict[str, list[Answer]] = {}
    levels: dict[str, str] = {}
    if completed:
        q = select(Answer).where(Answer.checkin_id.in_(completed)).order_by(Answer.created_at)  # type: ignore[attr-defined,arg-type]
        for a in session.exec(q).all():
            answers.setdefault(a.checkin_id, []).append(a)
        for e in session.exec(select(Escalation).where(Escalation.checkin_id.in_(completed))).all():  # type: ignore[attr-defined]
            levels[e.checkin_id] = rules.max_level(levels.get(e.checkin_id, NO_ESCALATION), e.level)

    cfg = content.signal_rules()
    terms = cfg["primary_terms"]
    calls = []
    for c in checkins:
        patient = patients[c.patient_id]
        grades: dict[str, int | None] = {}
        if c.status == COMPLETED:
            amap = answers_map(answers.get(c.id, []))
            baseline = baseline_of(patient)
            grades = {term: term_grade(term, amap, baseline) for term in terms}
        calls.append({"call_id": c.id, "subject_id": patient.subject_id, "date": local_date(_call_time(c)),
                      "status": c.status, "grades": grades, "level": levels.get(c.id, NO_ESCALATION)})
    dose_dates = {p.subject_id: list(p.dose_dates or []) for p in patients.values()}
    # The live site's AE log in the app holds only confirmed Between Visits drafts (origin between_visits), which
    # never match (REQ-024); the simulated site 101 log in site_ae.json belongs to simulated subjects and never
    # pools with MEASURED episodes. So no site AE rows are passed: live episodes are never matched.
    built = episodes.classify(episodes.build_episodes(calls, cfg), [], cfg, data_cut=data_cut_today(),
                              dose_dates=dose_dates)
    translations = _translations(session, (ep["checkin_ids"][0] for ep in built))

    out: list[SiteEpisode] = []
    for ep in built:
        first = by_id[ep["checkin_ids"][0]]
        patient = patients[first.patient_id]
        out.append(SiteEpisode(
            episode_id=f"ep_live_{first.id}_{ep['term']}", site_id=site_id, subject_id=ep["subject_id"],
            language=patient.language, pace=patient.pace, term=ep["term"], grade=ep["grade"], kind=ep["kind"],
            episode_date=ep["episode_date"], checkin_ids=list(ep["checkin_ids"]),
            # integrated by construction (docs/11 §2.4): past its entry window a live episode is not evaluated
            status=episodes.status_of(ep, not_evaluated=True), paged_level=ep["paged_level"],
            matched_site_ae_id=ep["matched_site_ae_id"],
            evidence=_evidence(first, ep["term"], answers.get(first.id, []), translations.get(first.id, {})),
            data_origin=MEASURED,
        ))
    return sorted(out, key=lambda e: (e.episode_date, e.episode_id), reverse=True)


# ---- answer key, validation summary, equity --------------------------------------------------------------


def answer_key() -> AnswerKeyOut:
    """`GET /api/site-signal/answer-key`: `answer_key.json` as written; the confusion counts are run.py's."""
    path = get_settings().monitoring_out / ANSWER_KEY
    doc: AnswerKeyFile = _guard(ANSWER_KEY, lambda: _load(path, AnswerKeyFile))
    return AnswerKeyOut(run_id=COMMITTED_RUN_ID, data_origin=SIMULATED, answer_key=doc.answer_key,
                        confusion=doc.confusion)


def _pass_through(path: Path, shape: Any, missing_code: str, shown: str) -> Any:
    try:
        _stamp(path)
    except FileNotFoundError as exc:
        raise ApiError(HTTPStatus.NOT_FOUND, missing_code, f"{shown} not found") from exc
    return _guard(shown, lambda: _load(path, shape))


def validation_summary() -> SiteSignalValidationOut:
    """`GET /api/site-signal/validation`: `validation/site_signal/summary.json` verbatim plus `data_origin`;
    404 `no_validation_run` when the file is missing."""
    return _pass_through(get_settings().site_signal_summary, SiteSignalValidationOut, "no_validation_run",
                         "validation/site_signal/summary.json")


def equity() -> EquityOut:
    """`GET /api/site-signal/equity`: `equity.json` as written; 404 `no_equity_run` when it is missing."""
    return _pass_through(get_settings().monitoring_out / EQUITY, EquityOut, "no_equity_run",
                         f"monitoring/out/{EQUITY}")
