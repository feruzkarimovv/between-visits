"""Demo controls (enabled only when DEMO_MODE=1; otherwise 404 demo_disabled)."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.errors import ApiError
from app.schemas import OkOut, ReplayOut, ReplaySpeed, ScenarioOut
from app.services import replay

router = APIRouter(prefix="/api/demo", tags=["demo"])


def require_demo() -> None:
    if not get_settings().demo_controls_enabled:
        raise ApiError(404, "demo_disabled", "Demo controls are off (set DEMO_MODE=1).")


@router.get("/scenarios", response_model=list[ScenarioOut], dependencies=[Depends(require_demo)])
def scenarios() -> list[ScenarioOut]:
    return [ScenarioOut(**s) for s in replay.list_scenarios()]


@router.get(
    "/scenarios/{scenario_id}/audio",
    response_class=FileResponse,
    dependencies=[Depends(require_demo)],
    responses={
        200: {"description": "The scenario's call audio.",
              "content": {"audio/mpeg": {"schema": {"type": "string", "format": "binary"}}}},
        404: {"description": "Error `demo_disabled`, `scenario_not_found` or `audio_not_found`."},
    },
)
def scenario_audio(scenario_id: str) -> FileResponse:
    """`scenarios/audio/<id>.mp3` as audio/mpeg (docs/03 §6.2; demo only, any role, no audit).

    The mp3 is gitignored and exists only where someone put it; serving a recorded call's audio on the public
    instance needs the written consent of the teammate who played the patient (otherwise transcript-only).
    """
    return FileResponse(replay.scenario_audio_file(scenario_id), media_type="audio/mpeg")


@router.post("/replay/{scenario_id}", response_model=ReplayOut, dependencies=[Depends(require_demo)])
def replay_scenario(
    scenario_id: str,
    speed: ReplaySpeed | None = Query(
        default=None, description="Playback multiplier: 1, 2 or 4 (2 = twice real time). Default: REPLAY_SPEED, else 2."
    ),
    session: Session = Depends(get_session),
) -> ReplayOut:
    """Starts the replay in the background (docs/03 §6.2); any speed other than 1, 2 or 4 is 422 validation_error."""
    return ReplayOut(checkin_id=replay.start(session, scenario_id, speed=None if speed is None else float(speed)))


@router.post("/reset", response_model=OkOut, dependencies=[Depends(require_demo)])
def reset() -> OkOut:
    from app.seed import reset_and_seed

    reset_and_seed()
    return OkOut()
