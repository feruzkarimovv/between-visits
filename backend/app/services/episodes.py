"""Site Signal episodes: construction, matching, evaluability, paged stratum and status (task B16).

Implements docs/11-site-signal-sap.md §4 (episodes), §5 (matching) and §6 (evaluability, paged stratum,
status precedence) exactly. This is the one implementation, shared by the backend (the site 101 live
bridge in `services/site_signal.py`) and by `monitoring/` (imported through `bvsignal/_backend.py`, never
re-implemented). Its sha256 is frozen by the `sap-v1` tag (`params.yaml` `frozen_inputs`).

Pure functions over plain dicts, lists and tuples: standard library only, no database, no file I/O, no
logging, no LLM. Every constant comes from `cfg`, the parsed `data/signal_rules.json` (in the backend
`app.content.signal_rules()`). Grades come from `rules.py` and are never re-derived here; the only thing
taken from `rules.py` is the order of escalation levels (`LEVEL_RANK`). Inputs are never mutated.

Pass a whole study (or site) per call: reading `cfg` costs a few microseconds per call. Per subject the
work is one sort of its calls and one sort of its candidate AE rows plus their eligible (episode, row)
pairs, so O(n log n) for any real call schedule. Output order is deterministic: subjects in order of
first appearance, then episode date, then the order of `primary_terms`.

Dates
-----
A date value (`DateLike`) is a `datetime.date`, an ISO "YYYY-MM-DD" string, or an integer day number
(int or any integer type, e.g. numpy). Calendar values (dates and strings) may be mixed; day numbers must
be used for every date of a call (calls, AE rows, dose dates, data cut, end of AE collection) and must
share one scale, e.g. study day. A `datetime` is refused with TypeError: a call's date is the DISPLAY_TZ
local date of the call (`timeutil.local_date`), which the caller computes, never the UTC date.

Output dates keep the input's type: `episode_date` and `last_call_date` are the input values themselves,
and `anchor_date` is either a call's date or `episode_date - gap_days` in the type of `episode_date`.

Inputs
------
call (dict), any number of subjects in any order:
    call_id     str       opaque key copied into `checkin_ids` (DB `ci_` id, or a simulation call key)
    subject_id  str
    date        DateLike  DISPLAY_TZ local date of the call. Same-day calls keep their input order, so
                          pass them in time order.
    status      str       only "completed" calls contribute to episodes (§6.3)
    grades      dict      primary term -> g_k, the provisional grade on this call, or None. The caller derives
                          it from the call's answers exactly as docs/11 §4.2 says (`rules.grade()` never
                          returns 0): for a term whose items were asked, 0 when `rules.term_present(term,
                          answers)` is false, else `rules.grade(term, answers, baseline).provisional_grade`
                          (None when grade_basis is "needs_clinician"); None when the term was not asked or
                          its only answers are `unknown` / `not_measured`. None or a missing term skips the
                          call for that term (§4.2 rule 6). Optional; other terms are ignored.
    level       str       highest escalation level raised on the call: "none" | "callback" | "urgent" |
                          "emergency". Optional (default none). cfg `paged.levels` page an episode (§6.2).
    Live bridge (site 101): date = `timeutil.local_date` of the check-in's start; grades by the §4.2
    mapping above from the check-in's answers and the patient's baseline (the same mapping the simulator
    applies, so not from Finding rows alone: a Finding can exist for a term reported absent when a red
    flag is attributed to it); level = the highest level of its Escalation rows.

site AE row (dict), SDTM-style, `SiteAE` in docs/02:
    site_ae_id  str       copied into `matched_site_ae_id` (read by `classify` only)
    subject_id  str
    aeseq       int       tie-break (§5)
    aeterm      str       mapped to a primary term through cfg `match.term_synonyms` after lower-casing
                          and trimming; exact match, an unmapped term never matches
    aestdtc     DateLike
    entered_on  DateLike  the row is in the log at the data cut only if entered_on <= data_cut
    origin      str       only "site" rows are candidates; cfg `match.exclude_origins` ("between_visits",
                          confirmed Between Visits drafts) never match (§2.2, REQ-024)
    `symptomatic` and `aetoxgr` are not read: §5 defines candidates by origin, entry date, subject and
    mapped term, and a grade disagreement is not a mismatch.

dose_dates: {subject_id: [DateLike, ...]}, the subject's actual dose visit dates (delays included, §3),
    extended past the data cut where the schedule is known. The first one strictly after the episode date
    is the "next scheduled dose visit" of §6.1. A subject with none after the episode date is pending.
ae_end (optional): {subject_id: DateLike}, the last day of the subject's AE collection (discontinuation,
    withdrawal or death, §3). An episode dated after it is never evaluable.

Output: episode (dict)
----------------------
build_episodes() returns:
    subject_id, term
    grade           int       band: the grade at the opening call (2 or 3); never lowered (§4.2 rule 2)
    kind            str       "new" | "worsened"
    episode_date    DateLike  D_e, the date of the first folded call (§4.3)
    last_call_date  DateLike  date of the last folded call
    anchor_date     DateLike  L_e (§5): date of the subject's last completed call before D_e with a non-null
                              grade for the term below `min_grade` (new) or below the band (worsened);
                              D_e - gap_days when there is none or it is more than gap_days before D_e
    checkin_ids     list[str] call_ids of the folded calls, in date order. (checkin_ids[0], term) is unique,
                              e.g. the live episode id `ep_live_{checkin_ids[0]}_{term}` (docs/02).
    paged_level     str|None  highest cfg `paged.levels` level raised on a folded call (§6.2). With
                              page_proximal=True (sensitivity SE14, §12.6) also the highest such page of the
                              subject on any call, completed or not, within `paged.proximity_days` of D_e;
                              SE14 adds to the folded-call rule, it never un-pages an episode.
classify() / analyze() return copies that add:
    evaluable           bool      §6.1 at the data cut
    matched_site_ae_id  str|None  the one-to-one matched row (§5); paged and pending episodes are matched too
    status              str       "paged" | "pending" | "matched" | "unmatched" (§6.4). "not_evaluated" needs
                                  the leave-one-site-out rates and the site guards, so the caller sets it with
                                  `status_of(episode, not_evaluated=True)`, which keeps the precedence.

Functions
---------
build_episodes(calls, cfg, *, page_proximal=False) -> [episode]            §4
match(episodes, site_aes, cfg, *, data_cut) -> [row index | None]           §5, parallel to `episodes`
is_evaluable(episode_date, next_dose_date, data_cut, cfg, *, ae_end=None)   §6.1
status_of(episode, *, not_evaluated=False) -> status                        §6.4
classify(episodes, site_aes, cfg, *, data_cut, dose_dates, ae_end=None)     §5, §6.1, §6.4
analyze(calls, site_aes, cfg, *, data_cut, dose_dates, ae_end=None, page_proximal=False)
                                                                            build_episodes + classify
paged_stratum(episodes) -> {"n", "matched"}                                 §6.2, per site, descriptive only
with_match_sensitivity(cfg, sensitivity_id) -> cfg                          SE1/SE2 windows (§12.6)
STATUSES (precedence order), ANALYSIS_SET_STATUSES (A_s), OE_STATUSES (enter O, E and V)
"""

from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta
from operator import index, itemgetter
from typing import Any, NamedTuple

from app.services.rules import LEVEL_RANK

DateLike = date | int | str
Record = Mapping[str, Any]

COMPLETED = "completed"
SITE_ORIGIN = "site"
NEW = "new"
WORSENED = "worsened"

PAGED = "paged"
PENDING = "pending"
NOT_EVALUATED = "not_evaluated"
MATCHED = "matched"
UNMATCHED = "unmatched"
STATUSES = (PAGED, PENDING, NOT_EVALUATED, MATCHED, UNMATCHED)  # §6.4 precedence, highest first
ANALYSIS_SET_STATUSES = frozenset({NOT_EVALUATED, MATCHED, UNMATCHED})  # A_s (§3, §6.4)
OE_STATUSES = frozenset({MATCHED, UNMATCHED})  # the only statuses that enter O, E and V

__all__ = [
    "ANALYSIS_SET_STATUSES",
    "OE_STATUSES",
    "STATUSES",
    "DateLike",
    "analyze",
    "build_episodes",
    "classify",
    "is_evaluable",
    "match",
    "paged_stratum",
    "status_of",
    "with_match_sensitivity",
]

_CompletedCall = tuple[int, DateLike, str, str | None, Mapping[str, Any]]  # day, date, call_id, level, grades
_NO_GRADES: Mapping[str, int | None] = {}
_by_day_then_input = itemgetter(0, 1)
_by_day = itemgetter(0)


class _Config(NamedTuple):
    primary_terms: tuple[str, ...]
    min_grade: int
    gap_days: int
    window_days: int
    lower_tolerance_days: int
    exclude_origins: frozenset[str]
    synonyms: dict[str, str]  # lower-cased, trimmed synonym -> primary term
    entry_window_days: int
    next_visit_plus_days: int
    paged_levels: frozenset[str]
    proximity_days: int


def _config(cfg: Mapping[str, Any]) -> _Config:
    """The constants this module reads from signal_rules.json; refuses settings the SAP does not specify."""
    episode, match_rules = cfg["episode"], cfg["match"]
    evaluability, paged = cfg["evaluability"], cfg["paged"]
    if episode["worsened_opens_new"] is not True:
        raise ValueError("signal_rules: episode.worsened_opens_new must be true (docs/11 §4.2 rule 3)")
    if match_rules["lower_anchor"] != "last_negative_call":
        raise ValueError("signal_rules: match.lower_anchor must be 'last_negative_call' (docs/11 §5)")
    if match_rules["one_to_one"] is not True:
        raise ValueError("signal_rules: match.one_to_one must be true (docs/11 §5)")
    unknown = set(paged["levels"]) - LEVEL_RANK.keys()
    if unknown:
        raise ValueError(f"signal_rules: unknown paged.levels {sorted(unknown)}")
    synonyms: dict[str, str] = {}
    for term, words in match_rules["term_synonyms"].items():
        for word in words:
            if synonyms.setdefault(word.strip().lower(), term) != term:
                raise ValueError(f"signal_rules: synonym {word!r} maps to two terms")
    return _Config(
        primary_terms=tuple(cfg["primary_terms"]),
        min_grade=cfg["min_grade"],
        gap_days=episode["gap_days"],
        window_days=match_rules["window_days"],
        lower_tolerance_days=match_rules["lower_tolerance_days"],
        exclude_origins=frozenset(match_rules["exclude_origins"]),
        synonyms=synonyms,
        entry_window_days=evaluability["entry_window_days"],
        next_visit_plus_days=evaluability["next_visit_plus_days"],
        paged_levels=frozenset(paged["levels"]),
        proximity_days=paged["proximity_days"],
    )


# ---- dates -------------------------------------------------------------------------------------------


def _day(value: DateLike) -> int:
    """Day number of a date value: an integer as is, a calendar date as its proleptic Gregorian ordinal."""
    if type(value) is int:
        return value
    if isinstance(value, datetime):
        raise TypeError("pass the DISPLAY_TZ local date of the call (timeutil.local_date), not a datetime")
    if isinstance(value, date):
        return value.toordinal()
    if isinstance(value, str):
        return date.fromisoformat(value).toordinal()
    if not isinstance(value, bool):
        try:
            return index(value)  # other integer types, e.g. numpy integers
        except TypeError:
            pass
    raise TypeError(f"not a date value: {value!r}")


def _shift(value: DateLike, days: int) -> DateLike:
    """`value` moved by `days`, in the type of `value` (a datetime never gets here: `_day` refuses it)."""
    if isinstance(value, date):
        return value + timedelta(days=days)
    if isinstance(value, str):
        return (date.fromisoformat(value) + timedelta(days=days)).isoformat()
    return _day(value) + days


def _higher(current: str | None, level: str) -> str:
    return level if current is None or LEVEL_RANK[level] > LEVEL_RANK[current] else current


# ---- §4 episodes ---------------------------------------------------------------------------------------


def build_episodes(
    calls: Iterable[Record], cfg: Mapping[str, Any], *, page_proximal: bool = False
) -> list[dict[str, Any]]:
    """New or worsened grade >= min_grade episodes of the primary terms (§4.2), with L_e and paged level."""
    c = _config(cfg)
    by_subject: dict[str, list[tuple[int, int, Record]]] = {}
    for n, call in enumerate(calls):
        by_subject.setdefault(call["subject_id"], []).append((_day(call["date"]), n, call))
    out: list[dict[str, Any]] = []
    for subject_id, rows in by_subject.items():
        rows.sort(key=_by_day_then_input)
        completed = [
            (day, call["date"], call["call_id"], call.get("level"), call.get("grades") or _NO_GRADES)
            for day, _, call in rows
            if call["status"] == COMPLETED  # §6.3: other calls contribute nothing for any term
        ]
        found = [
            (day, t, k, episode)
            for t, term in enumerate(c.primary_terms)
            for k, (day, episode) in enumerate(_term_episodes(subject_id, term, completed, c))
        ]
        if page_proximal and found:
            pages = [(day, call["level"]) for day, _, call in rows if call.get("level") in c.paged_levels]
            _add_proximal_pages(found, pages, c)
        found.sort(key=itemgetter(0, 1, 2))
        out.extend(episode for *_, episode in found)
    return out


def _term_episodes(
    subject_id: str, term: str, completed: list[_CompletedCall], c: _Config
) -> list[tuple[int, dict[str, Any]]]:
    """§4.2 rules 1-6 for one subject and term, over its completed calls in date order."""
    found: list[tuple[int, dict[str, Any]]] = []
    current: dict[str, Any] | None = None  # the open episode
    current_last = 0  # day of its last folded (reporting) call
    # grade -> (day, date) of the latest call with that grade on an earlier day, and the same for calls
    # earlier on the current day, kept apart because L_e is a call strictly before D_e
    earlier: dict[int, tuple[int, DateLike]] = {}
    same_day: dict[int, tuple[int, DateLike]] = {}
    this_day: int | None = None
    for day, when, call_id, level, grades in completed:
        grade = grades.get(term)
        if grade is None:  # rule 6: no gradable answer, skipped for this term; the gap rule still applies
            continue
        if day != this_day:
            earlier.update(same_day)
            same_day = {}
            this_day = day
        if current is not None and day - current_last > c.gap_days:
            current = None  # rule 5: the episode closed at its last reporting call
        if grade >= c.min_grade:
            if current is None or grade > current["grade"]:
                # rule 1 (new); rule 3 (worsened): the open episode closed at the previous call
                kind = NEW if current is None else WORSENED
                current = _open(subject_id, term, grade, kind, day, when, call_id, earlier, c)
                found.append((day, current))
            else:  # rule 2: same or lower grade folds in; a fall from 3 to 2 keeps band 3
                current["checkin_ids"].append(call_id)
                current["last_call_date"] = when
            current_last = day
            if level in c.paged_levels:  # §6.2: a page on any folded call, for any red flag
                current["paged_level"] = _higher(current["paged_level"], level)
        else:
            current = None  # rule 4: closes at the first completed call below min_grade
        same_day[grade] = (day, when)
    return found


def _open(
    subject_id: str,
    term: str,
    grade: int,
    kind: str,
    day: int,
    when: DateLike,
    call_id: str,
    earlier: dict[int, tuple[int, DateLike]],
    c: _Config,
) -> dict[str, Any]:
    """A new episode opened at this call, with its lower anchor L_e (§5 observation interval)."""
    below = c.min_grade if kind == NEW else grade
    prior = [day_date for g, day_date in earlier.items() if g < below]
    last_day, last_date = max(prior, key=_by_day) if prior else (None, None)
    if last_day is None or day - last_day > c.gap_days:
        anchor = _shift(when, -c.gap_days)
    else:
        anchor = last_date
    return {
        "subject_id": subject_id,
        "term": term,
        "grade": grade,
        "kind": kind,
        "episode_date": when,
        "last_call_date": when,
        "anchor_date": anchor,
        "checkin_ids": [call_id],
        "paged_level": None,
    }


def _add_proximal_pages(
    found: list[tuple[int, int, int, dict[str, Any]]], pages: list[tuple[int, str]], c: _Config
) -> None:
    """SE14 (§6.2, §12.6): also paged when any page of the subject is within proximity_days of D_e."""
    days = [day for day, _ in pages]
    for d_e, _, _, episode in found:
        lo = bisect_left(days, d_e - c.proximity_days)
        hi = bisect_right(days, d_e + c.proximity_days)
        for _, level in pages[lo:hi]:
            episode["paged_level"] = _higher(episode["paged_level"], level)


# ---- §5 matching ----------------------------------------------------------------------------------------


def match(
    episodes: Sequence[Record], site_aes: Sequence[Record], cfg: Mapping[str, Any], *, data_cut: DateLike
) -> list[int | None]:
    """One-to-one greedy match of episodes to site AE rows (§5). Returns, per episode, the index of its row
    in `site_aes` or None.

    Runs over all of a subject's episodes for the term, paged, pending and evaluable alike, so a row explained
    by a paged episode is not reused by a neighbouring one. A row is eligible for an episode when AESTDTC is
    in [L_e - lower_tolerance_days, D_e + window_days] (inclusive). Eligible pairs are taken in order of
    distance from AESTDTC to [L_e, D_e] (0 inside), then episode date, then aeseq, skipping used episodes
    and rows.
    """
    return _match(episodes, site_aes, _config(cfg), _day(data_cut))


def _match(episodes: Sequence[Record], site_aes: Sequence[Record], c: _Config, cut: int) -> list[int | None]:
    groups: dict[tuple[str, str], list[int]] = {}
    for i, episode in enumerate(episodes):
        groups.setdefault((episode["subject_id"], episode["term"]), []).append(i)
    subjects = {subject_id for subject_id, _ in groups}
    candidates: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for j, row in enumerate(site_aes):
        if row["subject_id"] not in subjects:
            continue
        origin = row["origin"]
        if origin in c.exclude_origins or origin != SITE_ORIGIN:  # §2.2, REQ-024
            continue
        if _day(row["entered_on"]) > cut:  # not yet in the log at the data cut
            continue
        term = c.synonyms.get(row["aeterm"].strip().lower())
        if term is None:  # unmapped terms never match
            continue
        key = (row["subject_id"], term)
        if key in groups:
            candidates.setdefault(key, []).append((_day(row["aestdtc"]), j))

    matched: list[int | None] = [None] * len(episodes)
    for key, rows in candidates.items():
        rows.sort()
        starts = [aestdtc for aestdtc, _ in rows]
        pairs: list[tuple[int, int, int, int, int]] = []
        for i in groups[key]:
            episode = episodes[i]
            d_e, l_e = _day(episode["episode_date"]), _day(episode["anchor_date"])
            lo = bisect_left(starts, l_e - c.lower_tolerance_days)
            hi = bisect_right(starts, d_e + c.window_days)
            for aestdtc, j in rows[lo:hi]:
                distance = l_e - aestdtc if aestdtc < l_e else max(aestdtc - d_e, 0)
                # input positions last, so exact ties stay deterministic
                pairs.append((distance, d_e, site_aes[j]["aeseq"], i, j))
        pairs.sort()
        used_rows: set[int] = set()
        for *_, i, j in pairs:
            if matched[i] is None and j not in used_rows:
                matched[i] = j
                used_rows.add(j)
    return matched


# ---- §6 evaluability, paged stratum and status ---------------------------------------------------------


def _evaluable(d_e: int, next_dose: int | None, cut: int, ae_end: int | None, c: _Config) -> bool:
    if next_dose is None or (ae_end is not None and d_e > ae_end):
        return False
    return cut >= max(d_e + c.entry_window_days, next_dose + c.next_visit_plus_days)


def is_evaluable(
    episode_date: DateLike,
    next_dose_date: DateLike | None,
    data_cut: DateLike,
    cfg: Mapping[str, Any],
    *,
    ae_end: DateLike | None = None,
) -> bool:
    """§6.1: data_cut >= max(episode date + entry_window_days, next dose visit + next_visit_plus_days).

    `next_dose_date` is the first dose visit strictly after the episode date. Without one, or for an episode
    dated after the end of AE collection (`ae_end`), the episode is not evaluable."""
    return _evaluable(
        _day(episode_date),
        None if next_dose_date is None else _day(next_dose_date),
        _day(data_cut),
        None if ae_end is None else _day(ae_end),
        _config(cfg),
    )


def status_of(episode: Record, *, not_evaluated: bool = False) -> str:
    """§6.4 precedence: paged > pending > not_evaluated > matched | unmatched.

    `episode` needs `paged_level`, `evaluable` and `matched_site_ae_id`. Pass not_evaluated=True when the
    episode's cell has no leave-one-site-out rate, or its site is not computed for `error` or
    `integrated_mode` (§8.1, §6.4)."""
    if episode["paged_level"] is not None:
        return PAGED
    if not episode["evaluable"]:
        return PENDING
    if not_evaluated:
        return NOT_EVALUATED
    return MATCHED if episode["matched_site_ae_id"] is not None else UNMATCHED


def classify(
    episodes: Sequence[Record],
    site_aes: Sequence[Record],
    cfg: Mapping[str, Any],
    *,
    data_cut: DateLike,
    dose_dates: Mapping[str, Iterable[DateLike]],
    ae_end: Mapping[str, DateLike] | None = None,
) -> list[dict[str, Any]]:
    """Copies of `episodes` with `evaluable`, `matched_site_ae_id` and `status` at the data cut (§5, §6)."""
    c = _config(cfg)
    cut = _day(data_cut)
    rows = _match(episodes, site_aes, c, cut)
    doses: dict[str, list[int]] = {}
    out: list[dict[str, Any]] = []
    for episode, j in zip(episodes, rows, strict=True):
        subject_id = episode["subject_id"]
        days = doses.get(subject_id)
        if days is None:
            days = doses[subject_id] = sorted(_day(d) for d in dose_dates.get(subject_id, ()))
        d_e = _day(episode["episode_date"])
        k = bisect_right(days, d_e)  # the next dose visit strictly after the episode date
        end = ae_end.get(subject_id) if ae_end else None
        next_dose = days[k] if k < len(days) else None
        evaluable = _evaluable(d_e, next_dose, cut, None if end is None else _day(end), c)
        site_ae_id = None
        if j is not None:
            site_ae_id = site_aes[j].get("site_ae_id")
            if not site_ae_id:
                raise ValueError(f"site AE row {j} has no site_ae_id")
        result = {**episode, "evaluable": evaluable, "matched_site_ae_id": site_ae_id}
        result["status"] = status_of(result)
        out.append(result)
    return out


def analyze(
    calls: Iterable[Record],
    site_aes: Sequence[Record],
    cfg: Mapping[str, Any],
    *,
    data_cut: DateLike,
    dose_dates: Mapping[str, Iterable[DateLike]],
    ae_end: Mapping[str, DateLike] | None = None,
    page_proximal: bool = False,
) -> list[dict[str, Any]]:
    """build_episodes() then classify(): every episode of `calls` with its match, evaluability and status."""
    episodes = build_episodes(calls, cfg, page_proximal=page_proximal)
    return classify(episodes, site_aes, cfg, data_cut=data_cut, dose_dates=dose_dates, ae_end=ae_end)


def paged_stratum(episodes: Iterable[Record]) -> dict[str, int]:
    """§6.2 `paged_stratum {n, matched}` over one site's classified episodes: descriptive, never in O/E."""
    paged = [episode for episode in episodes if episode["status"] == PAGED]
    return {"n": len(paged), "matched": sum(episode["matched_site_ae_id"] is not None for episode in paged)}


def with_match_sensitivity(cfg: Mapping[str, Any], sensitivity_id: str) -> dict[str, Any]:
    """A copy of `cfg` with the window of its `match.sensitivity` entry `sensitivity_id` (SE1, SE2, §12.6)."""
    for entry in cfg["match"]["sensitivity"]:
        if entry["id"] == sensitivity_id:
            window = {key: value for key, value in entry.items() if key != "id"}
            return {**cfg, "match": {**cfg["match"], **window}}
    raise KeyError(f"no match sensitivity {sensitivity_id!r} in signal_rules")
