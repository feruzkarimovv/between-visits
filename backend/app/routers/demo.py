"""Demo controls (enabled only when DEMO_MODE=1; otherwise 404 demo_disabled)."""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.errors import ApiError
from app.schemas import OkOut, ReplayOut, ScenarioOut
from app.services import replay

router = APIRouter(prefix="/api/demo", tags=["demo"])


def require_demo() -> None:
    if not get_settings().demo_controls_enabled:
        raise ApiError(404, "demo_disabled", "Demo controls are off (set DEMO_MODE=1).")


@router.get("/scenarios", response_model=list[ScenarioOut], dependencies=[Depends(require_demo)])
def scenarios() -> list[ScenarioOut]:
    return [ScenarioOut(**s) for s in replay.list_scenarios()]


@router.post("/replay/{scenario_id}", response_model=ReplayOut, dependencies=[Depends(require_demo)])
def replay_scenario(scenario_id: str, session: Session = Depends(get_session)) -> ReplayOut:
    return ReplayOut(checkin_id=replay.start(session, scenario_id))


@router.post("/reset", response_model=OkOut, dependencies=[Depends(require_demo)])
def reset() -> OkOut:
    from app.seed import reset_and_seed

    reset_and_seed()
    return OkOut()
