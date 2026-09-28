import numpy as np
import pandas as pd

from app.analysis.monsoon import DrySpellConfig, OnsetConfig, detect_dry_spells, detect_onset


def series(year, values_by_offset, start="06-01", length=140, fill=0.0):
    idx = pd.date_range(f"{year}-{start}", periods=length, freq="D")
    s = pd.Series(fill, index=idx, dtype=float)
    for off, v in values_by_offset.items():
        s.iloc[off] = v
    return s


def test_onset_detected_at_first_day_of_qualifying_wet_spell():
    # 3-day wet spell of 25 mm on day 10, then regular rain -> onset Jun 11
    vals = {10: 10, 11: 8, 12: 7}
    vals.update({d: 3.0 for d in range(13, 60, 3)})
    r = detect_onset(series(2020, vals), 2020)
    assert r.status == "detected" and str(r.onset_date) == "2020-06-11"


def test_false_start_followed_by_long_dry_spell_is_skipped():
    vals = {5: 12, 6: 10, 7: 6}             # wet spell, then nothing for >7 days -> false start
    vals.update({40: 15, 41: 10, 42: 8})    # real onset Jul 11 (offset 40), then rain continues
    vals.update({d: 4.0 for d in range(43, 90, 3)})
    r = detect_onset(series(2020, vals), 2020)
    assert r.status == "detected" and str(r.onset_date) == "2020-07-11"


def test_no_onset_when_no_wet_spell():
    r = detect_onset(series(2020, {}), 2020)
    assert r.status == "not_detected" and r.onset_date is None


def test_missing_data_is_reported_not_guessed():
    r = detect_onset(pd.Series(dtype=float, index=pd.DatetimeIndex([])), 2020)
    assert r.status == "insufficient_data"


def test_configurable_thresholds_change_result():
    vals = {10: 6, 11: 5, 12: 4}            # 15 mm in 3 days
    vals.update({d: 3.0 for d in range(13, 60, 3)})
    s = series(2020, vals)
    assert detect_onset(s, 2020).status == "not_detected"
    assert detect_onset(s, 2020, OnsetConfig(wet_window_mm=12.0)).status == "detected"


def test_dry_spell_with_resumption_and_tag():
    vals = {d: 10.0 for d in range(0, 10)}  # wet first 10 days
    for d in range(10, 17):
        vals[d] = 0.0                       # 7-day dry spell
    vals[17] = 12.0
    s = series(2020, vals, fill=5.0)
    spells = detect_dry_spells(s, 2020)
    assert len(spells) == 1
    sp = spells[0]
    assert (sp.length, sp.ended_by, str(sp.resumption_date), sp.scope) == (7, "rain", "2020-06-18", "local_dry_spell")


def test_short_dry_runs_are_ignored_and_min_length_configurable():
    vals = {d: 0.0 for d in range(10, 13)}  # 3 dry days
    s = series(2020, vals, fill=6.0)
    assert detect_dry_spells(s, 2020) == []
    assert len(detect_dry_spells(s, 2020, DrySpellConfig(min_length=3))) == 1


def test_data_gap_ends_spell_without_inventing_resumption():
    s = series(2020, {}, fill=6.0)
    for d in range(10, 16):
        s.iloc[d] = 0.0
    s.iloc[16] = np.nan
    sp = detect_dry_spells(s, 2020)[0]
    assert sp.ended_by == "data_gap_or_end" and sp.resumption_date is None


def test_spells_before_onset_can_be_excluded():
    s = series(2020, {d: 0.0 for d in range(2, 9)}, fill=6.0)
    assert len(detect_dry_spells(s, 2020, onset_date=pd.Timestamp("2020-06-20").date())) == 0
