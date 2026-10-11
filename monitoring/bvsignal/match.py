"""Coverage, minimum-data status and the analysis set of Site Signal (docs/11-site-signal-sap.md §4-§8.1). SIMULATED.

What lives where
----------------
* Episodes (§4), matching (§5), evaluability (§6.1), the paged stratum (§6.2) and status precedence (§6.4)
  come from ``app.services.episodes`` (task B16) through ``bvsignal._backend``: the one implementation shared
  with the backend's site 101 live bridge. This module never re-implements them. It calls
  ``episodes.analyze`` once per site, ``episodes.status_of`` to set ``not_evaluated`` (so the §6.4 precedence
  stays the shared one) and ``episodes.paged_stratum`` for the descriptive paged counts.
* This module adds what needs the whole study: site coverage, the §7 checks in order, the study-level
  ``min_sites`` minimum, the leave-one-site-out capture rates of §8.1 (an episode whose cell and term have no
  such rate is ``not_evaluated``, §6.4) and each site's O, E and V of §8.1 (check 5 fails when V_s = 0).
  ``indicators.py`` reads O, E and V from here and adds z, the overdispersion adjustment, tiers and rank
  (§8.2-§8.3); it never recomputes them.

Every constant (match window, evaluability, paged levels, minimum data, site roles, excluded origins) comes
from ``data/signal_rules.json``; this file holds no numeric literal other than 0, 1 and -1 (AST check,
REQ-023). No LLM anywhere on this path (CLAUDE.md rule 1). A site that is not computed never gets a tier
other than ``not_computed`` (REQ-025): capture discordance is a reason to look, not a finding.

Order of work for one study (:func:`analyze_sites`)
---------------------------------------------------
1. The rule file and the data cut are checked once; a bad one fails the whole study (the caller reports it,
   e.g. the backend's 503 ``site_signal_unavailable``), never a single site.
2. Per site, inside one ``try``: inputs, coverage, ``origin = between_visits`` rows and site-role draft actions
   (§2.4), and ``episodes.analyze``. Any exception sets ``error`` (§7 order 1); otherwise a ``between_visits`` row
   or a site-role draft action sets ``integrated_mode`` (order 2).
3. Leave-one-site-out rates over the A-episodes (evaluable, not paged) of every site that is not excluded for
   ``error`` or ``integrated_mode`` (§8.1); O, E and V per such site. An exception there is order 1 too:
   the site becomes ``error`` and the rates are recomputed without it.
4. ``not_evaluated`` (§6.4): an evaluable, non-paged episode at an ``error`` or ``integrated_mode`` site, or
   one whose cell and term have no leave-one-site-out rate. Paged and pending episodes keep their status.
5. Checks 3-5 in order for the remaining sites (coverage < ``min_call_completion``; patients <
   ``min_patients``; |A_s| < ``min_evaluable_episodes`` or V_s = 0), then check 6: fewer than ``min_sites``
   sites passing 1-5 gives every one of them ``study_below_min_sites``.

Sites not computed for coverage or data keep their episodes ``matched`` / ``unmatched`` (valid data, shown in
the drill-down, citable in a site query) and still contribute to the other sites' rates (§6.4, §8.1).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bvsignal import DATA_ORIGIN, REPO_ROOT
from bvsignal._backend import episodes

if TYPE_CHECKING:
    from bvsignal.simulate import Study

SIGNAL_RULES_FILE = REPO_ROOT / "data" / "signal_rules.json"

# not_computed_reason values, in the docs/11 §7 order (the first failing check wins)
ERROR = "error"
INTEGRATED_MODE = "integrated_mode"
LOW_COVERAGE = "low_coverage"
INSUFFICIENT_PATIENTS = "insufficient_patients"
INSUFFICIENT_EPISODES = "insufficient_episodes"
STUDY_BELOW_MIN_SITES = "study_below_min_sites"
REASONS = (ERROR, INTEGRATED_MODE, LOW_COVERAGE, INSUFFICIENT_PATIENTS, INSUFFICIENT_EPISODES, STUDY_BELOW_MIN_SITES)
# §8.1: these sites add nothing to the other sites' rates, and their evaluable episodes are not_evaluated (§6.4)
EXCLUDED_FROM_RATES = frozenset({ERROR, INTEGRATED_MODE})
NOT_COMPUTED = "not_computed"  # the only tier a site with a reason ever gets (docs/03 §5.1, REQ-025)

# Scenario analysis settings (simulate.Scenario.analysis, docs/11 §12.6) applied here; SE21's overdispersion
# setting belongs to indicators.py and is passed through untouched.
MATCH_WINDOW_KEYS = ("match_window_days", "lower_tolerance_days")  # SE1, SE2: an entry of signal_rules match.sensitivity
PAGED_RULE_KEY, PAGE_PROXIMAL = "paged_rule", "page_proximal"  # SE14
NEXT_VISIT_KEY = "next_visit_plus_days"  # SE20
INDICATOR_KEYS = frozenset({"overdispersion"})  # SE21

Cell = tuple[str, int]  # (term, grade band)


# ---- inputs and outputs ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SiteData:
    """One site's inputs at the data cut, as plain data in the shapes of ``app.services.episodes``.

    ``subject_ids`` are the site's enrolled patients (§7 check 4). ``calls`` and ``site_aes`` are every call and
    every AE-log row of those subjects (any origin; ``between_visits`` rows make the site integrated, §2.4).
    ``scheduled_calls`` and ``completed_calls`` count the site's calls with scheduled date <= data cut (§7 check
    3). ``draft_action_roles`` are the roles of the actors of draft actions at the site in the analysis window.
    ``load_error`` marks a site whose inputs could not be loaded (§7 order 1)."""

    site_id: str
    subject_ids: Sequence[str]
    calls: Sequence[Mapping[str, Any]]
    site_aes: Sequence[Mapping[str, Any]]
    dose_dates: Mapping[str, Iterable[Any]]
    scheduled_calls: int
    completed_calls: int
    ae_end: Mapping[str, Any] | None = None
    draft_action_roles: Sequence[str] = ()
    load_error: str | None = None


@dataclass
class SiteMatch:
    """One site's analysis set and §7 status.

    ``episodes`` are copies of the ``episodes.analyze`` output with ``episode_id`` (``ep_{site}_{n}``),
    ``site_id`` and ``data_origin`` added and ``status`` final (§6.4). ``p_hat`` is parallel to ``episodes``:
    the leave-one-site-out rate of each episode that enters O, E and V, else None. ``O``, ``E``, ``V`` and
    ``n_clusters`` (patients contributing to them) are the §8.1 sums for every site that is not excluded for
    ``error`` or ``integrated_mode``; they are statistics only when ``computed`` (:meth:`row` nulls them
    otherwise). ``error`` describes the exception behind reason ``error``, never silent."""

    site_id: str
    data_origin: str = DATA_ORIGIN
    n_patients: int | None = None
    scheduled_calls: int | None = None
    completed_calls: int | None = None
    call_completion: float | None = None
    integrated: bool = False
    episodes: list[dict[str, Any]] = field(default_factory=list)
    p_hat: list[float | None] = field(default_factory=list)
    O: int | None = None  # noqa: E741 (the SAP's symbol)
    E: float | None = None
    V: float | None = None
    n_clusters: int | None = None
    not_computed_reason: str | None = None
    error: str | None = None

    @property
    def computed(self) -> bool:
        """Passed every §7 check (only then do O, E and V enter z, tiers and rank)."""
        return self.not_computed_reason is None

    def count(self, statuses: Iterable[str]) -> int:
        wanted = frozenset(statuses)
        return sum(ep["status"] in wanted for ep in self.episodes)

    @property
    def n_episodes_evaluable(self) -> int:
        """|A_s|: evaluable, non-paged episodes (statuses not_evaluated, matched, unmatched; §3, §6.4)."""
        return self.count(episodes.ANALYSIS_SET_STATUSES)

    @property
    def n_pending(self) -> int:
        return self.count((episodes.PENDING,))

    @property
    def n_paged(self) -> int:
        return self.count((episodes.PAGED,))

    @property
    def paged_stratum(self) -> dict[str, int]:
        """§6.2 ``{n, matched}``: descriptive only, never in O, E or V."""
        return episodes.paged_stratum(self.episodes)

    def row(self) -> dict[str, Any]:
        """The ``SiteSignalRow`` fields this module owns (docs/02); indicators.py adds z, tiers and rank."""
        on = self.computed
        return {
            "site_id": self.site_id,
            "n_patients": self.n_patients,
            "n_episodes_evaluable": self.n_episodes_evaluable,
            "n_pending": self.n_pending,
            "n_paged": self.n_paged,
            "call_completion": self.call_completion,
            "O": self.O if on else None,
            "E": self.E if on else None,
            "V": self.V if on else None,
            "tier": None if on else NOT_COMPUTED,
            "not_computed_reason": self.not_computed_reason,
            "data_origin": self.data_origin,
        }


@dataclass
class StudyMatch:
    """Every site of one study after §5-§8.1, in input order."""

    sites: list[SiteMatch]
    data_cut: Any
    n_passing_sites: int  # sites that passed §7 checks 1-5
    min_sites: int
    data_origin: str = DATA_ORIGIN

    @property
    def study_not_computed_reason(self) -> str | None:
        return STUDY_BELOW_MIN_SITES if self.n_passing_sites < self.min_sites else None

    @property
    def n_computed_sites(self) -> int:
        return sum(s.computed for s in self.sites)

    def site(self, site_id: str) -> SiteMatch:
        for s in self.sites:
            if s.site_id == site_id:
                return s
        raise KeyError(f"no site {site_id!r} in this study")

    def episodes(self) -> list[dict[str, Any]]:
        return [ep for s in self.sites for ep in s.episodes]

    def rows(self) -> list[dict[str, Any]]:
        return [s.row() for s in self.sites]


# ---- configuration ------------------------------------------------------------------------------------------


def load_signal_rules(path: Path = SIGNAL_RULES_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def analysis_config(cfg: Mapping[str, Any], analysis: Mapping[str, Any] | Iterable[tuple[str, Any]] | None = None
                    ) -> tuple[dict[str, Any], bool]:
    """The rule file under a scenario's analysis settings (docs/11 §12.6), and whether SE14 applies.

    SE1/SE2 name their window by value; it must be an entry of ``match.sensitivity`` in signal_rules.json,
    applied with ``episodes.with_match_sensitivity``. SE14 is ``episodes``' page-proximal rule; SE20 replaces
    ``evaluability.next_visit_plus_days``. Unknown settings are refused, never ignored."""
    settings = dict(analysis or {})
    out: dict[str, Any] = dict(cfg)
    if any(k in settings for k in MATCH_WINDOW_KEYS):
        if not all(k in settings for k in MATCH_WINDOW_KEYS):
            raise ValueError(f"a match-window scenario sets both {MATCH_WINDOW_KEYS}, got {sorted(settings)}")
        window = tuple(int(settings.pop(k)) for k in MATCH_WINDOW_KEYS)
        ids = [e["id"] for e in cfg["match"]["sensitivity"]
               if (int(e["window_days"]), int(e["lower_tolerance_days"])) == window]
        if len(ids) != 1:
            raise ValueError(f"match window {window} is not one entry of signal_rules match.sensitivity")
        out = episodes.with_match_sensitivity(out, ids[0])
    page_proximal = False
    if PAGED_RULE_KEY in settings:
        rule = settings.pop(PAGED_RULE_KEY)
        if rule != PAGE_PROXIMAL:
            raise ValueError(f"unknown paged rule {rule!r} (docs/11 §12.6 SE14)")
        page_proximal = True
    if NEXT_VISIT_KEY in settings:
        out = {**out, "evaluability": {**out["evaluability"], NEXT_VISIT_KEY: int(settings.pop(NEXT_VISIT_KEY))}}
    unknown = set(settings) - INDICATOR_KEYS
    if unknown:
        raise ValueError(f"unknown analysis settings {sorted(unknown)} (docs/11 §12.6)")
    return out, page_proximal


# ---- the study --------------------------------------------------------------------------------------------------


def analyze_sites(
    sites: Sequence[SiteData],
    cfg: Mapping[str, Any] | None = None,
    *,
    data_cut: Any,
    analysis: Mapping[str, Any] | Iterable[tuple[str, Any]] | None = None,
    data_origin: str = DATA_ORIGIN,
) -> StudyMatch:
    """§5-§8.1 for one study: episodes and matches (``episodes.py``), coverage, the §7 checks, not_evaluated."""
    rules, page_proximal = analysis_config(load_signal_rules() if cfg is None else cfg, analysis)
    md = rules["minimum_data"]
    min_sites, min_patients = int(md["min_sites"]), int(md["min_patients"])
    min_episodes, min_completion = int(md["min_evaluable_episodes"]), float(md["min_call_completion"])
    integrated_origins = frozenset(rules["match"]["exclude_origins"])
    site_roles = frozenset(rules["integrated_mode"]["site_roles"])
    # step 1: the rule file and the data cut fail the study, never one site
    episodes.match((), (), rules, data_cut=data_cut)
    ids = [str(s.site_id) for s in sites]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate site ids {ids}")

    # step 2 (§7 orders 1-2)
    results = [_load_site(s, rules, data_cut, page_proximal, integrated_origins, site_roles, data_origin)
               for s in sites]

    # step 3 (§8.1); an exception there is §7 order 1 and the rates are recomputed without the site
    while True:
        included = [r for r in results if r.not_computed_reason not in EXCLUDED_FROM_RATES]
        totals = _cell_totals(included)
        failed = False
        for r in included:
            try:
                r.p_hat, r.O, r.E, r.V, r.n_clusters = _moments(r.episodes, totals)
            except Exception as exc:  # never silent: recorded as reason error with its message
                _fail(r, exc)
                failed = True
        if not failed:
            break

    # step 4 (§6.4): not_evaluated through the shared precedence
    for r in results:
        if r.not_computed_reason in EXCLUDED_FROM_RATES:
            r.p_hat = [None] * len(r.episodes)
            r.O = r.E = r.V = r.n_clusters = None
        for ep, p in zip(r.episodes, r.p_hat, strict=True):
            if ep["status"] in episodes.OE_STATUSES and p is None:
                ep["status"] = episodes.status_of(ep, not_evaluated=True)

    # step 5 (§7 orders 3-6)
    for r in results:
        if r.not_computed_reason is not None:
            continue
        if r.call_completion < min_completion:
            r.not_computed_reason = LOW_COVERAGE
        elif r.n_patients < min_patients:
            r.not_computed_reason = INSUFFICIENT_PATIENTS
        elif r.n_episodes_evaluable < min_episodes or not r.V > 0:
            r.not_computed_reason = INSUFFICIENT_EPISODES
    passing = [r for r in results if r.not_computed_reason is None]
    if len(passing) < min_sites:
        for r in passing:
            r.not_computed_reason = STUDY_BELOW_MIN_SITES
    return StudyMatch(sites=results, data_cut=data_cut, n_passing_sites=len(passing), min_sites=min_sites,
                      data_origin=data_origin)


def _fail(r: SiteMatch, exc: BaseException) -> None:
    r.not_computed_reason = ERROR
    r.error = f"{type(exc).__name__}: {exc}"


def _load_site(
    site: SiteData,
    rules: Mapping[str, Any],
    data_cut: Any,
    page_proximal: bool,
    integrated_origins: frozenset[str],
    site_roles: frozenset[str],
    data_origin: str,
) -> SiteMatch:
    """§7 orders 1-2 for one site: everything that can fail while loading or analysing it is in the try."""
    site_id = str(site.site_id)
    r = SiteMatch(site_id=site_id, data_origin=data_origin)
    try:
        if site.load_error is not None:
            raise RuntimeError(f"loading the site failed: {site.load_error}")
        subjects = [str(s) for s in site.subject_ids]
        known = frozenset(subjects)
        if len(known) != len(subjects):
            raise ValueError("duplicate subject ids")
        r.n_patients = len(subjects)
        scheduled, completed = int(site.scheduled_calls), int(site.completed_calls)
        if not 0 <= completed <= scheduled:
            raise ValueError(f"completed calls {completed} must be between 0 and scheduled calls {scheduled}")
        r.scheduled_calls, r.completed_calls = scheduled, completed
        # coverage = completed / scheduled (§7 check 3); no scheduled call is no coverage, never a pass
        r.call_completion = completed / scheduled if scheduled else 0.0
        for call in site.calls:
            if call["subject_id"] not in known:
                raise ValueError(f"call {call['call_id']!r} of subject {call['subject_id']!r} is not at this site")
        for row in site.site_aes:
            if row["subject_id"] not in known or str(row.get("site_id", site_id)) != site_id:
                raise ValueError(f"AE row {row.get('site_ae_id')!r} of subject {row['subject_id']!r} is not at this site")
        r.integrated = (any(row["origin"] in integrated_origins for row in site.site_aes)
                        or any(role in site_roles for role in site.draft_action_roles))
        found = episodes.analyze(site.calls, site.site_aes, rules, data_cut=data_cut, dose_dates=site.dose_dates,
                                 ae_end=site.ae_end, page_proximal=page_proximal)
        r.episodes = [{"episode_id": f"ep_{site_id}_{n}", "site_id": site_id, **ep, "data_origin": data_origin}
                      for n, ep in enumerate(found, start=1)]
    except Exception as exc:  # §7 order 1; never silent: the message is kept on the site
        _fail(r, exc)
        r.episodes = []
        return r
    if r.integrated:
        r.not_computed_reason = INTEGRATED_MODE
    return r


# ---- §8.1 leave-one-site-out rates, O, E and V ---------------------------------------------------------------


def _in_analysis_set(ep: Mapping[str, Any]) -> bool:
    """Evaluable and not paged (A_s before not_evaluated is set)."""
    return ep["status"] in episodes.ANALYSIS_SET_STATUSES


def _cell_counts(eps: Iterable[Mapping[str, Any]]) -> dict[Cell, list[int]]:
    """Per cell (term, band): [matched, total] over a site's A-episodes."""
    out: dict[Cell, list[int]] = {}
    for ep in eps:
        if _in_analysis_set(ep):
            c = out.setdefault((ep["term"], ep["grade"]), [0, 0])
            c[0] += ep["matched_site_ae_id"] is not None
            c[1] += 1
    return out


def _cell_totals(included: Iterable[SiteMatch]) -> dict[Cell, list[int]]:
    total: dict[Cell, list[int]] = {}
    for r in included:
        for cell, (o, n) in _cell_counts(r.episodes).items():
            t = total.setdefault(cell, [0, 0])
            t[0] += o
            t[1] += n
    return total


def loso_rate(cell: Cell, own: Mapping[Cell, Sequence[int]], totals: Mapping[Cell, Sequence[int]]) -> float | None:
    """p̂₋ₛ(c) of §8.1: the other sites' matched share in the cell; if the other sites have no episode in the
    cell, their share pooled over the term's bands; None if that is empty too (the episode is not_evaluated)."""
    none = (0, 0)
    o, n = (t - m for t, m in zip(totals.get(cell, none), own.get(cell, none), strict=True))
    if n > 0:
        return o / n
    term = cell[0]
    o = n = 0
    for c, (to, tn) in totals.items():
        if c[0] == term:
            mo, mn = own.get(c, none)
            o += to - mo
            n += tn - mn
    return o / n if n > 0 else None


def _moments(eps: Sequence[Mapping[str, Any]], totals: Mapping[Cell, Sequence[int]]
             ) -> tuple[list[float | None], int, float, float, int]:
    """p̂ per episode, and O, E, V and n_s of §8.1 over the site's episodes that have a rate.

    V = max(n/(n-1) * sum_i (sum_e (Y_e - p̂_e))^2, sum_e p̂_e (1 - p̂_e)), clustered by patient; with one
    contributing patient the cluster term is 0 (as in monitoring/planning/plan_power.py), so V is the binomial
    floor."""
    own = _cell_counts(eps)
    p_hat: list[float | None] = []
    o, e, binomial = 0, 0.0, 0.0
    residual: dict[str, float] = {}
    for ep in eps:
        p = loso_rate((ep["term"], ep["grade"]), own, totals) if _in_analysis_set(ep) else None
        p_hat.append(p)
        if p is None:
            continue
        y = 1 if ep["matched_site_ae_id"] is not None else 0
        o += y
        e += p
        binomial += p * (1 - p)
        residual[ep["subject_id"]] = residual.get(ep["subject_id"], 0.0) + (y - p)
    n = len(residual)
    squares = sum(r * r for r in residual.values())
    cluster = n / (n - 1) * squares if n > 1 else 0.0
    return p_hat, o, e, max(cluster, binomial), n


# ---- the simulated study (simulate.Study) -------------------------------------------------------------------------


def site_inputs(study: Study) -> list[SiteData]:
    """Each site's :class:`SiteData` from one simulated study (study-day dates; no ``between_visits`` rows and no
    draft actions exist in a simulation, §2.4). A site whose inputs cannot be assembled gets ``load_error``."""
    members: list[list[str]] = [[] for _ in study.sites.ids]
    for sid, s in zip(study.subject_ids, study.pat_site.tolist(), strict=True):
        members[s].append(sid)
    calls, aes, doses = study.episode_calls(), study.site_aes_by_subject(), study.dose_days()
    scheduled, completed = study.scheduled_and_completed()
    out = []
    for s, site_id in enumerate(study.sites.ids):
        try:
            ids = tuple(members[s])
            out.append(SiteData(
                site_id=site_id, subject_ids=ids,
                calls=[c for sid in ids for c in calls.get(sid, ())],
                site_aes=[row for sid in ids for row in aes.get(sid, ())],
                dose_dates={sid: doses[sid] for sid in ids},
                scheduled_calls=int(scheduled[s]), completed_calls=int(completed[s]),
            ))
        except Exception as exc:  # §7 order 1, reported on the site
            out.append(SiteData(site_id=site_id, subject_ids=(), calls=(), site_aes=(), dose_dates={},
                                scheduled_calls=0, completed_calls=0, load_error=f"{type(exc).__name__}: {exc}"))
    return out


def match_study(study: Study, cfg: Mapping[str, Any] | None = None) -> StudyMatch:
    """§5-§8.1 on a simulated study, under its scenario's analysis settings (SE1, SE2, SE14, SE20)."""
    rules = study.model.signal_rules if cfg is None else cfg
    return analyze_sites(site_inputs(study), rules, data_cut=study.data_cut, analysis=study.scenario.analysis,
                         data_origin=study.data_origin)
