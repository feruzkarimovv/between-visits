"""R3 / CAPA-002: values that are dates (not timestamps) use the DISPLAY_TZ local date of the call (docs/03 §6.4).

The clock is frozen at 2026-10-11T03:30:00Z, which is 23:30 EDT on Sat Oct 10: the UTC date (Oct 11) and the
local date (Oct 10) differ. No clock library: `utcnow` is monkeypatched on `app.timeutil` and on every loaded
`app.*` module that imported it by name; model default factories call `timeutil.utcnow()` at run time.
"""

import csv
import importlib
import pkgutil
import sys
from datetime import UTC, date, datetime

import pytest

from app.config import get_settings
from app.models import Patient
from app.services import replay
from app.timeutil import local_date
from tests.conftest import COORD, INVESTIGATOR

FROZEN = datetime(2026, 10, 11, 3, 30, tzinfo=UTC)  # 23:30 EDT, Sat Oct 10
LOCAL_DAY = "2026-10-10"
UTC_DAY = "2026-10-11"


@pytest.fixture
def new_york(monkeypatch):
    """DISPLAY_TZ pinned to the study site's zone, whatever a developer's .env says."""
    monkeypatch.setenv("DISPLAY_TZ", "America/New_York")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


@pytest.fixture
def frozen_clock(new_york, monkeypatch):
    import app
    from app import timeutil

    for mod in pkgutil.walk_packages(app.__path__, "app."):  # load every module so none keeps the real clock
        importlib.import_module(mod.name)
    real = timeutil.utcnow

    def frozen() -> datetime:
        return FROZEN

    patched = []
    for name, mod in list(sys.modules.items()):
        if (name == "app" or name.startswith("app.")) and getattr(mod, "utcnow", None) is real:
            monkeypatch.setattr(mod, "utcnow", frozen)
            patched.append(name)
    assert {"app.timeutil", "app.services.replay", "app.services.checkins", "app.services.sae"} <= set(patched)
    return FROZEN


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@pytest.mark.req("REQ-016")
@pytest.mark.parametrize(
    ("instant", "expected"),
    [
        pytest.param(datetime(2026, 10, 11, 3, 30, tzinfo=UTC), date(2026, 10, 10), id="edt-2330"),
        pytest.param(datetime(2026, 10, 11, 3, 59, 59, tzinfo=UTC), date(2026, 10, 10), id="edt-235959"),
        pytest.param(datetime(2026, 10, 11, 4, 0, tzinfo=UTC), date(2026, 10, 11), id="edt-midnight"),
        pytest.param(datetime(2026, 12, 2, 4, 59, tzinfo=UTC), date(2026, 12, 1), id="est-2359"),
        pytest.param(datetime(2026, 12, 2, 5, 0, tzinfo=UTC), date(2026, 12, 2), id="est-midnight"),
        pytest.param(datetime(2026, 10, 11, 3, 30), date(2026, 10, 10), id="naive-is-utc"),
    ],
)
def test_local_date(new_york, instant, expected):
    assert local_date(instant) == expected


@pytest.mark.req("REQ-016")
def test_late_evening_call_uses_local_dates(frozen_clock, client, session, fake_pager):
    rosa = session.get(Patient, "pat_rosa")
    assert rosa is not None
    # A dose dated the next local day (Oct 11) must not count as the last dose before an Oct 10 call.
    rosa.dose_dates = ["2026-09-16", "2026-10-07", UTC_DAY]
    session.add(rosa)
    session.commit()

    cid = replay.start(session, "rosa_es_urgent", speed=1000, run_async=False)

    detail = client.get(f"/api/checkins/{cid}").json()
    started = _ts(detail["checkin"]["started_at"])
    assert started == FROZEN and started.date().isoformat() == UTC_DAY  # the UTC date really is Oct 11

    # check-in day filter: listed under the local day, not the UTC day
    rows = client.get("/api/checkins", params={"date": LOCAL_DAY}).json()
    row = next((r for r in rows if r["id"] == cid), None)
    assert row is not None, f"check-in missing from {LOCAL_DAY}: {rows}"
    assert row["status"] in ("in_progress", "completed")
    assert cid not in {r["id"] for r in client.get("/api/checkins", params={"date": UTC_DAY}).json()}

    # patient timeline points carry the local call date
    patient = client.get("/api/patients/pat_rosa").json()
    points = [pt for t in patient["timeline"] for pt in t["points"] if pt["checkin_id"] == cid]
    assert points and {pt["date"] for pt in points} == {LOCAL_DAY}

    # confirm the AE (no onset given, so the call-date fallback applies) and make it serious
    drafts = client.get("/api/drafts", params={"checkin_id": cid}).json()
    ae = next(d for d in drafts if d["kind"] == "AE" and d["payload"].get("term") == "Diarrhea")
    assert not ae["payload"].get("onset_date")
    assert client.post(f"/api/drafts/{ae['id']}/confirm", json={}, headers=COORD).status_code == 200
    r = client.post(f"/api/drafts/{ae['id']}/investigator", json={
        "is_serious": True, "seriousness_criteria": ["hospitalization"], "relatedness": "possibly_related",
    }, headers=INVESTIGATOR)
    assert r.status_code == 200, r.text

    # SAE onset fallback and last-dose lookup use the local call date
    sae = client.get(f"/api/sae/{r.json()['sae_report']['id']}").json()
    assert sae["payload"]["reaction"]["onset_date"] == LOCAL_DAY
    assert sae["payload"]["suspect_product"]["last_dose_date"] == "2026-10-07"

    # ae.csv AESTDTC fallback uses the local call date (comment lines skipped, if any)
    text = client.get("/api/export/ae.csv").text
    ae_rows = list(csv.DictReader(line for line in text.splitlines() if not line.startswith("#")))
    exported = next(x for x in ae_rows if x["AESPID"] == cid and x["AETERM"] == "Diarrhea")
    assert exported["AESTDTC"] == LOCAL_DAY
