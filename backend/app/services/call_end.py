"""Finish a call now (docs/03 §6.12), so a demo can end early and still show everything the call produced.

* Replay: the rest of the scenario runs at once (answers, pages, acknowledgment, post-call drafts).
* Browser or phone call: after the call ends, the conversation is read from ElevenLabs
  (`GET /v1/convai/conversations/{id}`) and run through the same post-call pipeline as the webhook, instead of
  waiting for the webhook to arrive. Whichever comes first runs; process_post_call() ignores the second. If the read
  fails or times out, the webhook remains the path (nothing is lost).
"""

import logging
import threading
import time
from typing import Any, Literal

from sqlmodel import Session

from app.errors import ApiError
from app.models import CheckIn
from app.services import elevenlabs, replay
from app.timeutil import utcnow

log = logging.getLogger("bv.call_end")

POLL_S = 2.0
MAX_WAIT_S = 45.0  # ElevenLabs marks a conversation "done" a few seconds after it ends (analysis)
FinishMode = Literal["fast_forward", "pulling", "already_done"]


def finish(session: Session, c: CheckIn) -> FinishMode:
    if c.postcall_status in ("processing", "done"):
        return "already_done"
    if c.channel == "replay":
        if c.status == "in_progress" and replay.fast_forward(c.id):
            return "fast_forward"
        raise ApiError(409, "not_in_call", "This replay is not running.")
    if not c.el_conversation_id or c.status in ("scheduled", "cancelled"):
        raise ApiError(409, "not_in_call", "This check-in has no call to finish.")
    c.ended_at = c.ended_at or utcnow()
    session.add(c)
    threading.Thread(target=pull_post_call, args=(c.id, c.el_conversation_id), daemon=True,
                     name=f"finish-{c.id}").start()
    return "pulling"


def _ready(data: dict[str, Any]) -> bool:
    return data.get("status") in ("done", "failed")


def pull_post_call(checkin_id: str, conversation_id: str) -> None:
    """Poll the conversation until ElevenLabs has finished it, then run the post-call pipeline."""
    from app.routers.webhooks import process_post_call

    data: dict[str, Any] | None = None
    deadline = time.monotonic() + MAX_WAIT_S
    while True:
        try:
            data = elevenlabs.client().get_conversation(conversation_id)
        except Exception as e:  # noqa: BLE001  the webhook is still on its way
            log.warning("finish_pull_failed checkin_id=%s error=%s", checkin_id, e)
        if (data and _ready(data)) or time.monotonic() >= deadline:
            break
        time.sleep(POLL_S)
    if not data or not data.get("transcript"):
        log.warning("finish_pull_gave_up checkin_id=%s (waiting for the post-call webhook)", checkin_id)
        return
    log.info("finish_pull_done checkin_id=%s status=%s", checkin_id, data.get("status"))
    process_post_call({**data, "conversation_id": conversation_id})
