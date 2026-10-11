"""Site query flow (task B18): templated, non-leading data-completeness requests to one site.

Contract: docs/03 §5.4 (payloads and states), §5.6 (errors), §5.7 (audit); table: docs/02 § SiteQuery.

- Wording comes only from `data/site_queries.json` (rule 2): the body is rendered from the template with subject
  IDs, terms, dates and grades of the cited episodes, and a rendered text with an unfilled placeholder is never
  stored. The only free text is the CRA's edit while in draft, checked for patient names and banned phrases.
- Eligibility: every cited episode exists in the committed run, is at the queried site and is `unmatched`
  (including at a site not computed for low coverage or too little data). Only `sr_committed` is queryable.
- States: draft -> sent (CRA approves; delivery to the mock site inbox at the same instant) -> answered
  (coordinator) -> closed (CRA). Every step calls `write_audit` with the §5.7 action and before/after (rule 7).
- Subject IDs only: no patient name in any query text (REQ-027).

No LLM is imported on this path (REQ-021).
"""

import logging
import re
import unicodedata
from collections.abc import Iterable, Sequence
from http import HTTPStatus
from typing import Any, get_args

from sqlmodel import Session, select

from app import content
from app.audit import write_audit
from app.errors import ApiError
from app.ids import new_id
from app.models import AuditEvent, Patient, SiteQuery
from app.schemas import (
    COMMITTED_RUN_ID,
    AuditOut,
    SiteEpisode,
    SiteQueryDetailOut,
    SiteQueryEpisode,
    SiteQueryOut,
    SiteQueryResponseCodeOut,
    SiteQueryStatus,
)
from app.services import site_signal
from app.timeutil import iso, utcnow

log = logging.getLogger("bv.site_queries")

ENTITY = "SiteQuery"
DRAFT, SENT, ANSWERED, CLOSED = get_args(SiteQueryStatus)
STATUSES: tuple[str, ...] = get_args(SiteQueryStatus)
INBOX_STATUSES = frozenset({SENT, ANSWERED, CLOSED})  # what a coordinator (the mock site inbox) sees
OPEN_STATUSES = frozenset({SENT, ANSWERED})  # `open_queries` on GET /api/sites
CITABLE = "unmatched"
LIVE_EPISODE_PREFIX = "ep_live_"
# docs/02 § SiteQuery: the only placeholders a template may use; there is no name placeholder.
PLACEHOLDERS = frozenset({"site_id", "episode_lines", "subject_id", "term", "episode_date", "grade"})
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


# ---- data/site_queries.json ------------------------------------------------------------------------------


def _doc() -> dict[str, Any]:
    return content.site_queries()


def template(template_id: str) -> dict[str, Any]:
    t = _doc()["templates"].get(template_id)
    if t is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "template_not_found", f"site query template {template_id} not found")
    return t


def response_label(code: str | None) -> str | None:
    if code is None:
        return None
    return next((r["label_en"] for r in _doc()["response_codes"] if r["code"] == code), None)


def response_codes() -> list[str]:
    return [r["code"] for r in _doc()["response_codes"]]


def response_code_options() -> list[SiteQueryResponseCodeOut]:
    """`GET /api/site-queries/response-codes`: every coded response with its label, in file order."""
    return [SiteQueryResponseCodeOut(code=r["code"], label_en=r["label_en"]) for r in _doc()["response_codes"]]


def banned_phrases() -> list[str]:
    return [b.lower() for b in _doc()["banned_phrases_en"]]


# ---- rendering and text checks ---------------------------------------------------------------------------


def _fill(text: str, values: dict[str, str]) -> str:
    """Replace each `{placeholder}`; an unknown or unfilled placeholder or a stray brace is an error, never sent."""

    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in PLACEHOLDERS or name not in values:
            raise ValueError(f"site query template: placeholder {{{name}}} cannot be filled here")
        return values[name]

    out = _PLACEHOLDER.sub(sub, text)
    if "{" in out or "}" in out:
        raise ValueError("site query template: unfilled placeholder or stray brace after rendering")
    return out


def render(template_id: str, site_id: str, episodes: Sequence[SiteEpisode]) -> str:
    """The query body: one `episode_line_en` per cited episode, ordered by episode date (then ID)."""
    t = template(template_id)
    lines = [
        _fill(t["episode_line_en"], {"subject_id": ep.subject_id, "term": ep.term,
                                     "episode_date": ep.episode_date.isoformat(), "grade": str(ep.grade)})
        for ep in sorted(episodes, key=lambda e: (e.episode_date, e.episode_id))
    ]
    return _fill(t["body_en"], {"site_id": site_id, "episode_lines": "\n".join(lines)})


def _fold(s: str) -> str:
    """Lower-case and strip accents, so an unaccented spelling still matches a seeded name."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def _patient_names(session: Session) -> set[str]:
    """First and last names of every Patient in the database, folded (docs/03 §5.4)."""
    names: set[str] = set()
    for p in session.exec(select(Patient)).all():
        for n in (p.first_name, p.last_name):
            if n and n.strip():
                names.add(_fold(n.strip()))
    return names


def check_text(session: Session, text: str) -> None:
    """422 `validation_error` (empty), `contains_identifier` (a patient name, case-insensitive whole word) or
    `banned_phrase` (an entry of `banned_phrases_en`, case-insensitive)."""
    if not text.strip():
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", "The query text cannot be empty.")
    folded = _fold(text)
    if any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", folded) for n in _patient_names(session)):
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "contains_identifier",
                       "The query text contains a patient name. Site queries carry subject IDs only.")
    low = text.lower()
    for phrase in banned_phrases():
        at = low.find(phrase)
        if at >= 0:
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "banned_phrase",
                           f'The query text contains "{text[at:at + len(phrase)]}", which site queries may not use '
                           "(data/site_queries.json banned_phrases_en).")


def banned_phrases_in(text: str) -> list[str]:
    """Banned phrases (lower case) found in the text, case-insensitive."""
    low = text.lower()
    return [b for b in banned_phrases() if b in low]


# ---- serialization -------------------------------------------------------------------------------------


def data_origin(episode_ids: Iterable[str]) -> str:
    """All simulated SIMULATED, all live (site 101 bridge) MEASURED, a mix MIXED (docs/03 §5.4)."""
    live = {eid.startswith(LIVE_EPISODE_PREFIX) for eid in episode_ids}
    if live == {True}:
        return site_signal.MEASURED
    return site_signal.MIXED if live == {True, False} else site_signal.SIMULATED


def query_out(q: SiteQuery) -> SiteQueryOut:
    return SiteQueryOut(
        id=q.id, site_id=q.site_id, signal_run_id=q.signal_run_id, template_id=q.template_id,
        title_en=_doc()["templates"].get(q.template_id, {}).get("title_en", ""), body_en=q.body_en,
        edited=q.edited, episode_ids=list(q.episode_ids or []), subject_ids=list(q.subject_ids or []),
        status=q.status, created_by=q.created_by, created_at=q.created_at, approved_by=q.approved_by,  # type: ignore[arg-type]
        approved_at=q.approved_at, response_code=q.response_code, response_label_en=response_label(q.response_code),
        response_note=q.response_note, responded_by=q.responded_by, responded_at=q.responded_at,
        closed_by=q.closed_by, closed_at=q.closed_at, closure_note=q.closure_note,
        data_origin=data_origin(q.episode_ids or []),  # type: ignore[arg-type]
    )


# ---- episode lookup ------------------------------------------------------------------------------------


def _episodes_by_id(session: Session, ids: Iterable[str]) -> dict[str, SiteEpisode]:
    """The cited episodes found in the committed run (simulated) or the live bridge (site 101, MEASURED)."""
    wanted = set(ids)
    study = site_signal.committed_study()
    found = {ep.episode_id: ep for eps in study.episodes.values() for ep in eps if ep.episode_id in wanted}
    if any(eid.startswith(LIVE_EPISODE_PREFIX) for eid in wanted - found.keys()):
        for site_id, site in study.sites.items():
            if site.is_live_site:
                live = site_signal._guard("live episodes", lambda s=site_id: site_signal.live_episodes(session, s))
                for ep in live:
                    if ep.episode_id in wanted:
                        found[ep.episode_id] = ep
    return found


# ---- reads -----------------------------------------------------------------------------------------------


def parse_statuses(raw: str | None) -> frozenset[str] | None:
    """`?status=sent,answered` -> the set, None for no filter; 422 `validation_error` for an unknown status."""
    if raw is None:
        return None
    wanted = frozenset(part.strip() for part in raw.split(",") if part.strip())
    unknown = sorted(wanted - set(STATUSES))
    if unknown:
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error",
                       f"unknown site query status {', '.join(unknown)}; use {', '.join(STATUSES)}")
    return wanted or None


def _visible(role: str) -> frozenset[str]:
    """The coordinator (the mock inbox for whichever site was queried) never sees a draft."""
    return INBOX_STATUSES if role == "coordinator" else frozenset(STATUSES)


def list_queries(session: Session, role: str, *, site_id: str | None = None,
                 statuses: frozenset[str] | None = None) -> list[SiteQueryOut]:
    """`GET /api/site-queries`, newest first. cra and sponsor see every status at every site; the coordinator
    sees sent, answered and closed queries at every site (a `status=draft` filter returns [])."""
    allowed = _visible(role) if statuses is None else _visible(role) & statuses
    if not allowed:
        return []
    q = select(SiteQuery).where(SiteQuery.status.in_(sorted(allowed)))  # type: ignore[attr-defined]
    if site_id is not None:
        q = q.where(SiteQuery.site_id == site_id)
    rows = session.exec(q).all()
    return [query_out(r) for r in sorted(rows, key=lambda r: (r.created_at, r.id), reverse=True)]


def open_counts(session: Session) -> dict[str, int]:
    """Sent or answered queries per site (`open_queries` on GET /api/sites)."""
    out: dict[str, int] = {}
    for site_id in session.exec(select(SiteQuery.site_id).where(SiteQuery.status.in_(sorted(OPEN_STATUSES)))).all():  # type: ignore[attr-defined]
        out[site_id] = out.get(site_id, 0) + 1
    return out


def for_site(session: Session, site_id: str) -> list[SiteQueryOut]:
    """Every query at one site, newest first (the cra/sponsor drill-down)."""
    return list_queries(session, "cra", site_id=site_id)


def get(session: Session, query_id: str, role: str) -> SiteQuery:
    """The query, or 404 `site_query_not_found`; a draft requested by a coordinator is 404 too."""
    q = session.get(SiteQuery, query_id)
    if q is None or q.status not in _visible(role):
        raise ApiError(HTTPStatus.NOT_FOUND, "site_query_not_found", f"site query {query_id} not found")
    return q


def detail(session: Session, query_id: str, role: str) -> SiteQueryDetailOut:
    """`GET /api/site-queries/{id}`: the query, the cited episodes (evidence null for the coordinator, so the
    query stays non-leading) and its audit rows, oldest first."""
    q = get(session, query_id, role)
    ids = list(q.episode_ids or [])
    found = _episodes_by_id(session, ids)
    missing = [eid for eid in ids if eid not in found]
    if missing:
        log.warning("site_query_episodes_missing query_id=%s site_id=%s episode_ids=%s", q.id, q.site_id,
                    ",".join(missing))
    hide = role == "coordinator"
    episodes = [
        SiteQueryEpisode.model_validate({**found[eid].model_dump(), **({"evidence": None} if hide else {})})
        for eid in ids if eid in found
    ]
    audit = session.exec(
        select(AuditEvent).where(AuditEvent.entity_type == ENTITY, AuditEvent.entity_id == q.id)
        .order_by(AuditEvent.seq)  # type: ignore[arg-type]
    ).all()
    return SiteQueryDetailOut(**query_out(q).model_dump(), episodes=episodes,
                              audit=[AuditOut(**a.model_dump()) for a in audit])


# ---- state machine -------------------------------------------------------------------------------------


def _log(action: str, q: SiteQuery, role: str) -> None:
    log.info("site_query.%s query_id=%s site_id=%s role=%s status=%s", action, q.id, q.site_id, role, q.status)


def create(session: Session, *, site_id: str, episode_ids: Sequence[str], template_id: str,
           signal_run_id: str | None, user: str, role: str) -> SiteQuery:
    """POST /api/site-queries: render a draft from the template; audit `site_query.drafted`."""
    run_id = signal_run_id or COMMITTED_RUN_ID
    if run_id != COMMITTED_RUN_ID:
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "run_not_queryable",
                       f"Only {COMMITTED_RUN_ID} can be queried; blind runs keep per-site results, not episodes.")
    ids = list(dict.fromkeys(eid.strip() for eid in episode_ids if eid.strip()))
    if not ids:
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", "Cite at least one episode.")
    template(template_id)
    study = site_signal.committed_study()
    if site_id not in study.sites:
        raise ApiError(HTTPStatus.NOT_FOUND, "site_not_found", f"site {site_id} is not in run {run_id}")
    found = _episodes_by_id(session, ids)
    cited: list[SiteEpisode] = []
    for eid in ids:
        ep = found.get(eid)
        if ep is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "episode_not_found", f"episode {eid} not found in run {run_id}")
        if ep.site_id != site_id:
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "episode_not_eligible",
                           f"episode {eid} is at site {ep.site_id}, not site {site_id}")
        if ep.status != CITABLE:
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "episode_not_eligible",
                           f"episode {eid} is {ep.status}; only unmatched episodes can be cited")
        cited.append(ep)

    body = render(template_id, site_id, cited)
    if banned_phrases_in(body):  # the approved template itself must never carry a banned phrase
        raise ValueError(f"site query template {template_id}: rendered text contains a banned phrase")
    q = SiteQuery(id=new_id("sq"), site_id=site_id, signal_run_id=run_id, template_id=template_id, episode_ids=ids,
                  subject_ids=sorted({ep.subject_id for ep in cited}), body_en=body, status=DRAFT, created_by=user)
    session.add(q)
    write_audit(session, actor=user, role=role, action="site_query.drafted", entity_type=ENTITY, entity_id=q.id,
                before=None, after={"site_id": site_id, "signal_run_id": run_id, "template_id": template_id,
                                    "episode_ids": ids, "status": DRAFT})
    _log("drafted", q, role)
    return q


def edit(session: Session, q: SiteQuery, body_en: str, note: str | None, user: str, role: str) -> SiteQuery:
    """PATCH: CRA edits the body while in draft; audit `site_query.edited` with before/after body."""
    if q.status != DRAFT:
        raise ApiError(HTTPStatus.CONFLICT, "not_draft", f"Site query is already {q.status}.")
    check_text(session, body_en)
    before = {"body_en": q.body_en}
    q.body_en, q.edited = body_en, True
    session.add(q)
    write_audit(session, actor=user, role=role, action="site_query.edited", entity_type=ENTITY, entity_id=q.id,
                before=before, after={"body_en": body_en}, note=note)
    _log("edited", q, role)
    return q


def approve(session: Session, q: SiteQuery, user: str, role: str) -> SiteQuery:
    """CRA approval = delivery to the mock site inbox at the same instant; audit `site_query.approved`."""
    if q.status != DRAFT:
        raise ApiError(HTTPStatus.CONFLICT, "not_draft", f"Site query is already {q.status}.")
    q.status, q.approved_by, q.approved_at = SENT, user, utcnow()
    session.add(q)
    write_audit(session, actor=user, role=role, action="site_query.approved", entity_type=ENTITY, entity_id=q.id,
                before={"status": DRAFT}, after={"status": SENT, "approved_at": iso(q.approved_at)})
    _log("approved", q, role)
    return q


def respond(session: Session, q: SiteQuery, response_code: str, note: str | None, user: str, role: str) -> SiteQuery:
    """Coordinator's coded response; audit `site_query.answered`."""
    if q.status != SENT:
        raise ApiError(HTTPStatus.CONFLICT, "not_sent", f"Site query is {q.status}, not sent.")
    if response_code not in response_codes():
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_response_code",
                       f"response_code must be one of {', '.join(response_codes())}")
    q.status, q.response_code, q.response_note = ANSWERED, response_code, note
    q.responded_by, q.responded_at = user, utcnow()
    session.add(q)
    write_audit(session, actor=user, role=role, action="site_query.answered", entity_type=ENTITY, entity_id=q.id,
                before={"status": SENT}, after={"status": ANSWERED, "response_code": response_code}, note=note)
    _log("answered", q, role)
    return q


def close(session: Session, q: SiteQuery, note: str | None, user: str, role: str) -> SiteQuery:
    """CRA closes an answered query; audit `site_query.closed`."""
    if q.status != ANSWERED:
        raise ApiError(HTTPStatus.CONFLICT, "not_answered", f"Site query is {q.status}, not answered.")
    q.status, q.closed_by, q.closed_at, q.closure_note = CLOSED, user, utcnow(), note
    session.add(q)
    write_audit(session, actor=user, role=role, action="site_query.closed", entity_type=ENTITY, entity_id=q.id,
                before={"status": ANSWERED}, after={"status": CLOSED}, note=note)
    _log("closed", q, role)
    return q
