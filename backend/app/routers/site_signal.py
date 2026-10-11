"""Site Signal routes (docs/03 §5.2-5.4, roles §6.1). Thin: logic lives in services/site_signal.py (reads, B17)
and services/site_queries.py (the site query flow, B18).

Reads are not audited (docs/03 §5.2); every site query write is (§5.7). The role check runs before the route
body, so a wrong role is 403 `wrong_role` even while the outputs are unavailable; an allowed role then gets 503
`site_signal_unavailable`.
"""

from http import HTTPStatus

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.routers.api import Actor, require_role
from app.schemas import (
    COMMITTED_RUN_ID,
    AnswerKeyOut,
    EquityOut,
    SiteDetailOut,
    SiteQueryApproveIn,
    SiteQueryCloseIn,
    SiteQueryCreateIn,
    SiteQueryDetailOut,
    SiteQueryOut,
    SiteQueryPatchIn,
    SiteQueryRespondIn,
    SiteSignalValidationOut,
    SitesOut,
)
from app.services import site_queries, site_signal

router = APIRouter(prefix="/api", tags=["site-signal"])

# cra, sponsor: the site rankings, drill-down, answer key and equity views (docs/03 §6.1)
signal_viewer = require_role("cra", "sponsor", action="view Site Signal site rankings")
# site queries (docs/03 §5.2): CRA drafts, edits, approves and closes; the coordinator (mock site inbox) responds
query_reader = require_role("cra", "sponsor", "coordinator", action="view site queries")
query_author = require_role("cra", action="draft, edit, approve or close a site query")
query_responder = require_role("coordinator", action="respond to a site query")


@router.get("/sites", response_model=SitesOut)
def sites(_: Actor = Depends(signal_viewer), session: Session = Depends(get_session)) -> SitesOut:
    return site_signal.sites_overview(session)


@router.get("/sites/{site_id}", response_model=SiteDetailOut)
def site_detail(
    site_id: str,
    run_id: str = Query(default=COMMITTED_RUN_ID),
    status: str | None = Query(default=None, description="comma-separated episode statuses to list"),
    _: Actor = Depends(signal_viewer),
    session: Session = Depends(get_session),
) -> SiteDetailOut:
    return site_signal.site_detail(session, site_id, run_id=run_id, statuses=site_signal.parse_statuses(status))


@router.get("/site-signal/answer-key", response_model=AnswerKeyOut)
def answer_key(_: Actor = Depends(signal_viewer)) -> AnswerKeyOut:
    return site_signal.answer_key()


@router.get("/site-signal/validation", response_model=SiteSignalValidationOut)
def validation() -> SiteSignalValidationOut:
    """Any role."""
    return site_signal.validation_summary()


@router.get("/site-signal/equity", response_model=EquityOut)
def equity(_: Actor = Depends(signal_viewer)) -> EquityOut:
    return site_signal.equity()


# ---- site queries (B18, docs/03 §5.4) --------------------------------------------------------------------------


@router.post("/site-queries", response_model=SiteQueryOut, status_code=HTTPStatus.CREATED)
def create_site_query(body: SiteQueryCreateIn, who: Actor = Depends(query_author),
                      session: Session = Depends(get_session)) -> SiteQueryOut:
    q = site_queries.create(session, site_id=body.site_id, episode_ids=body.episode_ids, template_id=body.template_id,
                            signal_run_id=body.signal_run_id, user=who.user, role=who.role)
    session.commit()
    return site_queries.query_out(q)


@router.get("/site-queries", response_model=list[SiteQueryOut])
def list_site_queries(
    site_id: str | None = Query(default=None),
    status: str | None = Query(default=None, description="comma-separated: draft, sent, answered, closed"),
    who: Actor = Depends(query_reader),
    session: Session = Depends(get_session),
) -> list[SiteQueryOut]:
    return site_queries.list_queries(session, who.role, site_id=site_id,
                                     statuses=site_queries.parse_statuses(status))


@router.get("/site-queries/{query_id}", response_model=SiteQueryDetailOut)
def get_site_query(query_id: str, who: Actor = Depends(query_reader),
                   session: Session = Depends(get_session)) -> SiteQueryDetailOut:
    return site_queries.detail(session, query_id, who.role)


@router.patch("/site-queries/{query_id}", response_model=SiteQueryOut)
def edit_site_query(query_id: str, body: SiteQueryPatchIn, who: Actor = Depends(query_author),
                    session: Session = Depends(get_session)) -> SiteQueryOut:
    q = site_queries.edit(session, site_queries.get(session, query_id, who.role), body.body_en, body.note,
                          who.user, who.role)
    session.commit()
    return site_queries.query_out(q)


@router.post("/site-queries/{query_id}/approve", response_model=SiteQueryOut)
def approve_site_query(query_id: str, body: SiteQueryApproveIn | None = None, who: Actor = Depends(query_author),
                       session: Session = Depends(get_session)) -> SiteQueryOut:
    q = site_queries.approve(session, site_queries.get(session, query_id, who.role), who.user, who.role)
    session.commit()
    return site_queries.query_out(q)


@router.post("/site-queries/{query_id}/respond", response_model=SiteQueryOut)
def respond_site_query(query_id: str, body: SiteQueryRespondIn, who: Actor = Depends(query_responder),
                       session: Session = Depends(get_session)) -> SiteQueryOut:
    q = site_queries.respond(session, site_queries.get(session, query_id, who.role), body.response_code, body.note,
                             who.user, who.role)
    session.commit()
    return site_queries.query_out(q)


@router.post("/site-queries/{query_id}/close", response_model=SiteQueryOut)
def close_site_query(query_id: str, body: SiteQueryCloseIn | None = None, who: Actor = Depends(query_author),
                     session: Session = Depends(get_session)) -> SiteQueryOut:
    q = site_queries.close(session, site_queries.get(session, query_id, who.role), body.note if body else None,
                           who.user, who.role)
    session.commit()
    return site_queries.query_out(q)
