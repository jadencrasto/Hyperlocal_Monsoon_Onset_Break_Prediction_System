"""Rainfall-only onset and dry-spell detection. All thresholds are configurable.

IMPORTANT - what these are and are not
* `detect_onset` is an *agronomic-style local onset proxy* (a wet spell that is not followed by a long
  dry spell), in the style of Stern et al. (1981) / Marteau et al. (2009). It is NOT the official IMD
  onset declaration, which uses multi-station rainfall, winds and OLR over Kerala and the advance
  of the monsoon front. The default thresholds are common choices, not calibrated for any block.
* `detect_dry_spells` finds *local rainfall dry spells*. A true meteorological "monsoon break"
  (IMD: monsoon trough shifting toward the Himalayan foothills, large-scale rainfall deficit) cannot
  be identified from one point's rain gauge or one grid cell. Every result is tagged
  scope="local_dry_spell" so the UI never presents it as an official break.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

MD = tuple[int, int]


@dataclass(frozen=True)
class OnsetConfig:
    search_start: MD = (6, 1)
    search_end: MD = (7, 31)
    wet_window_days: int = 3
    wet_window_mm: float = 20.0     # total rain in the wet window
    first_day_min_mm: float = 1.0   # onset day itself must be rainy
    dry_day_mm: float = 1.0         # a day below this is "dry" for the follow-up check
    dry_spell_days: int = 7         # a dry run this long invalidates the candidate
    follow_days: int = 20           # look-ahead window after the wet window


@dataclass(frozen=True)
class OnsetResult:
    year: int
    status: str                     # detected | not_detected | insufficient_data
    onset_date: date | None
    detail: str


@dataclass(frozen=True)
class DrySpellConfig:
    season_start: MD = (6, 1)
    season_end: MD = (9, 30)
    min_length: int = 5
    dry_day_mm: float = 2.5         # IMD "rainy day" threshold is >= 2.5 mm


@dataclass(frozen=True)
class DrySpell:
    start: date
    end: date
    length: int
    total_mm: float
    resumption_date: date | None    # first day rain >= threshold after the spell, if observed
    ended_by: str                   # rain | season_end | data_gap_or_end
    scope: str = "local_dry_spell"


def _daily(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> np.ndarray:
    """Values for every day in [start, end]; missing days are NaN."""
    s = series.copy()
    s.index = pd.DatetimeIndex(pd.to_datetime(s.index)).normalize()
    s = s[~s.index.duplicated(keep="last")]
    return s.reindex(pd.date_range(start, end, freq="D")).to_numpy(dtype=float)


def _max_run(flags: np.ndarray) -> int:
    best = run = 0
    for f in flags:
        run = run + 1 if f else 0
        best = max(best, run)
    return best


def detect_onset(series: pd.Series, year: int, cfg: OnsetConfig = OnsetConfig()) -> OnsetResult:
    start = pd.Timestamp(year, *cfg.search_start)
    end = pd.Timestamp(year, *cfg.search_end)
    w = cfg.wet_window_days
    arr = _daily(series, start, end + pd.Timedelta(days=w + cfg.follow_days))
    n_search = (end - start).days + 1
    skipped = 0
    for i in range(n_search):
        window = arr[i:i + w]
        if np.isnan(window).any():
            skipped += 1
            continue
        if arr[i] < cfg.first_day_min_mm or window.sum() < cfg.wet_window_mm:
            continue
        follow = arr[i + w:i + w + cfg.follow_days]
        if np.isnan(follow).any():
            skipped += 1   # cannot confirm the candidate without the look-ahead data
            continue
        if _max_run(follow < cfg.dry_day_mm) >= cfg.dry_spell_days:
            continue
        onset = (start + pd.Timedelta(days=i)).date()
        note = ("Local agronomic-style onset proxy, not the IMD declaration."
                + (" Earlier days had missing data, so the true onset may be earlier." if skipped else ""))
        return OnsetResult(year, "detected", onset, note)
    if skipped:
        return OnsetResult(year, "insufficient_data", None,
                           f"No onset confirmed and {skipped} candidate days lacked data; cannot conclude.")
    return OnsetResult(year, "not_detected", None, "No qualifying wet spell in the search window.")


def detect_dry_spells(series: pd.Series, year: int, cfg: DrySpellConfig = DrySpellConfig(),
                      onset_date: date | None = None) -> list[DrySpell]:
    start = pd.Timestamp(year, *cfg.season_start)
    end = pd.Timestamp(year, *cfg.season_end)
    n = (end - start).days + 1
    arr = _daily(series, start, end + pd.Timedelta(days=1))  # one extra day to see what ended a run
    thr = cfg.dry_day_mm
    spells: list[DrySpell] = []
    i = 0
    while i < n:
        if np.isnan(arr[i]) or arr[i] >= thr:
            i += 1
            continue
        j = i
        while j < n and not np.isnan(arr[j]) and arr[j] < thr:
            j += 1
        length = j - i
        if j >= n:
            ended_by, resumption = "season_end", None
        elif np.isnan(arr[j]):
            ended_by, resumption = "data_gap_or_end", None
        else:
            ended_by, resumption = "rain", (start + pd.Timedelta(days=j)).date()
        s_date = (start + pd.Timedelta(days=i)).date()
        if length >= cfg.min_length and (onset_date is None or s_date >= onset_date):
            spells.append(DrySpell(s_date, (start + pd.Timedelta(days=j - 1)).date(), length,
                                   float(np.nansum(arr[i:j])), resumption, ended_by))
        i = j
    return spells
