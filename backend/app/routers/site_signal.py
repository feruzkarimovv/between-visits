"""Site Signal read routes (task B17; docs/03 §5.2-5.3, roles §6.1). Thin: logic lives in services/site_signal.py.

Reads are not audited (docs/03 §5.2). The role check runs before the route body, so a wrong role is 403
`wrong_role` even while the outputs are unavailable; an allowed role then gets 503 `site_signal_unavailable`.
"""

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.routers.api import Actor, require_role
from app.schemas import (
    COMMITTED_RUN_ID,
    AnswerKeyOut,
    EquityOut,
    SiteDetailOut,
    SiteSignalValidationOut,
    SitesOut,
)
from app.services import site_signal

router = APIRouter(prefix="/api", tags=["site-signal"])

# cra, sponsor: the site rankings, drill-down, answer key and equity views (docs/03 §6.1)
signal_viewer = require_role("cra", "sponsor", action="view Site Signal site rankings")


@router.get("/sites", response_model=SitesOut)
def sites(_: Actor = Depends(signal_viewer)) -> SitesOut:
    return site_signal.sites_overview()


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
