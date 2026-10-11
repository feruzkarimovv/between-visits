"""Parametric roster of a simulated Site Signal study (docs/11-site-signal-sap.md §11.2 step 1). SIMULATED.

Every number comes from ``monitoring/params.yaml``:

* sites: the first ``n_sites`` of ``design.site_ids`` (101-120); ``design.live_site`` (101, Hillside Cancer
  Center, fictional) is the live demo site and is always honest (the simulator never plants a role there);
* patients per site: uniform integers over the design range, both ends inclusive (§11.5), unless a planted
  role fixes the count (``small_site``);
* Spanish-speaking share by site: Beta(``roster.spanish_share_by_site``), unless a planted role fixes it
  (``language_gap``); each patient is Spanish-speaking with the site's share;
* age: Normal(``roster.age``); extra-time pace when age >= ``roster.extra_time.min_age``;
* enrollment day: uniform integer on [0, ``design.enrollment_spread_days``].

Site names are fictional and end in "(fictional)"; regions are generic US region labels. Subject IDs follow
``{site}-{nnn}`` (docs/02 § Site Signal); no names anywhere. The optional Synthea language/age mix (S10) is a
labeled sensitivity analysis only and is not part of this module.

No LLM, no network, no file output: a pure function of the generator, params and the design.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

FICTIONAL_SUFFIX = "(fictional)"
SPANISH = "es"
ENGLISH = "en"
EXTRA_TIME = "extra_time"
STANDARD = "standard"

# Fictional site directory: site id -> (name, generic US region). 101 is the live demo site of
# data/study.json. Names are invented for this simulation; none is a real hospital.
SITE_DIRECTORY: dict[str, tuple[str, str]] = {
    "101": ("Hillside Cancer Center (fictional)", "Northeast"),
    "102": ("Bluebell Valley Oncology (fictional)", "Midwest"),
    "103": ("Cobblestone Cancer Clinic (fictional)", "Northeast"),
    "104": ("Driftwood Bay Oncology (fictional)", "West"),
    "105": ("Elm Hollow Cancer Care (fictional)", "South"),
    "106": ("Foxglove Regional Oncology (fictional)", "Midwest"),
    "107": ("Granite Pass Cancer Center (fictional)", "West"),
    "108": ("Heron Creek Oncology (fictional)", "South"),
    "109": ("Indigo Meadow Cancer Clinic (fictional)", "South"),
    "110": ("Juniper Flats Oncology (fictional)", "West"),
    "111": ("Kestrel Point Cancer Care (fictional)", "Northeast"),
    "112": ("Maple Ridge Oncology (fictional)", "Midwest"),
    "113": ("Lantern Hill Cancer Center (fictional)", "Northeast"),
    "114": ("Mossbank Oncology Group (fictional)", "Midwest"),
    "115": ("Nettlefield Cancer Clinic (fictional)", "South"),
    "116": ("Orchard Lane Oncology (fictional)", "West"),
    "117": ("Quillfeather Cancer Care (fictional)", "Midwest"),
    "118": ("Saltmarsh Oncology Partners (fictional)", "South"),
    "119": ("Tamarack Bend Cancer Center (fictional)", "West"),
    "120": ("Willowmere Oncology (fictional)", "Northeast"),
}

# Per-site overrides a planted role may set (docs/11 §11.4); every other role key acts on capture or
# completion and is applied by simulate.py.
ROSTER_OVERRIDES = ("patients", "spanish_share")


@dataclass(frozen=True)
class Sites:
    """The study's sites, in site-id order."""

    ids: tuple[str, ...]
    names: tuple[str, ...]
    regions: tuple[str, ...]
    live_index: int

    @property
    def n(self) -> int:
        return len(self.ids)


@dataclass(frozen=True)
class Roster:
    """One simulated roster. Site arrays have one entry per site, patient arrays one per patient (site-major)."""

    sites: Sites
    n_patients: np.ndarray  # [S] int
    spanish_share: np.ndarray  # [S] float, the site's Beta draw or a planted value
    pat_site: np.ndarray  # [P] int, site index
    subject_ids: tuple[str, ...]  # [P] "{site}-{nnn}"
    enroll_day: np.ndarray  # [P] int, study day of enrollment (first dose)
    age: np.ndarray  # [P] float, years
    spanish: np.ndarray  # [P] bool
    extra_time: np.ndarray  # [P] bool

    @property
    def n_patients_total(self) -> int:
        return int(self.pat_site.size)

    def language(self) -> list[str]:
        return [SPANISH if s else ENGLISH for s in self.spanish.tolist()]

    def pace(self) -> list[str]:
        return [EXTRA_TIME if x else STANDARD for x in self.extra_time.tolist()]


def study_sites(params: Mapping[str, Any], n_sites: int | None = None) -> Sites:
    """The first ``n_sites`` of ``design.site_ids`` (default ``design.n_sites``) with their fictional names."""
    design = params["design"]
    n = int(design["n_sites"] if n_sites is None else n_sites)
    all_ids = [str(s) for s in design["site_ids"]]
    if not 0 < n <= len(all_ids):
        raise ValueError(f"n_sites must be between 1 and {len(all_ids)}, got {n}")
    ids = tuple(all_ids[:n])
    live = str(design["live_site"])
    if live not in ids:
        raise ValueError(f"the live site {live} must be one of the study's sites {ids}")
    missing = [s for s in ids if s not in SITE_DIRECTORY]
    if missing:
        raise ValueError(f"no fictional name for sites {missing}")
    return Sites(
        ids=ids,
        names=tuple(SITE_DIRECTORY[s][0] for s in ids),
        regions=tuple(SITE_DIRECTORY[s][1] for s in ids),
        live_index=ids.index(live),
    )


def draw_roster(
    rng: np.random.Generator,
    params: Mapping[str, Any],
    sites: Sites,
    patients_per_site: Sequence[int],
    overrides: Mapping[int, Mapping[str, Any]] | None = None,
) -> Roster:
    """Draw one roster (docs/11 §11.2 step 1) in a fixed order: patients per site, Spanish share per site,
    then per patient the enrollment day, age and language. ``overrides`` maps a site index to planted
    roster values (``patients``, ``spanish_share``); they replace the draws after all site draws, so the
    number of random draws does not depend on the roles."""
    roster_p, design = params["roster"], params["design"]
    lo, hi = (int(v) for v in patients_per_site)
    if not 0 < lo <= hi:
        raise ValueError(f"patients_per_site must be a range lo <= hi with lo >= 1, got {patients_per_site}")
    S = sites.n
    n_patients = rng.integers(lo, hi, size=S, endpoint=True)
    share_p = roster_p["spanish_share_by_site"]
    if share_p["dist"] != "beta":
        raise ValueError("roster.spanish_share_by_site must be a beta distribution (docs/11 §11.3)")
    spanish_share = rng.beta(float(share_p["a"]), float(share_p["b"]), size=S)
    for s, spec in (overrides or {}).items():
        unknown = set(spec) - set(ROSTER_OVERRIDES)
        if unknown:
            raise ValueError(f"unknown roster override {sorted(unknown)}")
        if s == sites.live_index:
            raise ValueError("the live site is always honest; no role is planted there (docs/11 §11.4)")
        if "patients" in spec:
            n_patients[s] = int(spec["patients"])
        if "spanish_share" in spec:
            spanish_share[s] = float(spec["spanish_share"])
    pat_site = np.repeat(np.arange(S), n_patients)
    P = int(pat_site.size)
    enroll_day = rng.integers(0, int(design["enrollment_spread_days"]), size=P, endpoint=True)
    age_p = roster_p["age"]
    if age_p["dist"] != "normal":
        raise ValueError("roster.age must be a normal distribution (docs/11 §11.3)")
    age = rng.normal(float(age_p["mean"]), float(age_p["sd"]), size=P)
    spanish = rng.random(P) < spanish_share[pat_site]
    rule = roster_p["extra_time"]
    if rule["rule"] != "age_gte":
        raise ValueError("roster.extra_time.rule must be age_gte (docs/11 §11.2 step 1)")
    extra_time = age >= float(rule["min_age"])
    subject_ids = tuple(
        f"{sites.ids[s]}-{k:03d}" for s, n in enumerate(n_patients.tolist()) for k in range(1, n + 1)
    )
    return Roster(
        sites=sites,
        n_patients=n_patients,
        spanish_share=spanish_share,
        pat_site=pat_site,
        subject_ids=subject_ids,
        enroll_day=enroll_day,
        age=age,
        spanish=spanish,
        extra_time=extra_time,
    )
