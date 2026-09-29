"""ML plumbing tests. The rainfall below is a synthetic TEST FIXTURE used only to check that the
pipeline runs and behaves correctly (no leakage, correct splits). It says nothing about real skill."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.ml.features import FEATURES, TargetConfig, build_dataset, feature_frame, target_series
from app.ml.infer import InsufficientHistory, load_artifact, predict_break_risk
from app.ml import train as mltrain
from app.ml.train import (_bss, bootstrap_bss, by_location_metrics, calibration_diagnostics,
                          per_year_metrics, required_years, split_years, train_and_evaluate)


def synthetic(years, seed=0):
    rng = np.random.default_rng(seed)
    parts = []
    for y in years:
        idx = pd.date_range(f"{y}-05-01", f"{y}-10-15", freq="D")
        wet, vals = False, []
        for _ in idx:
            wet = rng.random() < (0.75 if wet else 0.3)
            vals.append(rng.gamma(2.0, 6.0) if wet else rng.random() * 1.5)
        parts.append(pd.Series(vals, index=idx))
    return pd.concat(parts)


def test_features_do_not_use_future_data():
    s = synthetic([2015])
    base = feature_frame(s)
    t = pd.Timestamp("2015-07-20")
    altered = s.copy()
    altered[altered.index > t] = 999.0       # change ONLY the future
    assert np.allclose(base.loc[:t].dropna().to_numpy(), feature_frame(altered).loc[:t].dropna().to_numpy())


def test_target_definition_exact():
    idx = pd.date_range("2020-07-01", periods=20, freq="D")
    p = pd.Series(10.0, index=idx)
    p.iloc[6:11] = 0.0                        # 5 dry days at offsets 6..10
    y = target_series(p, TargetConfig(horizon_days=7, dry_len=5))
    # window t+1..t+7 fully contains offsets 6..10 only for t = 3, 4, 5
    assert list(y.iloc[0:3]) == [0, 0, 0]
    assert list(y.iloc[3:6]) == [1, 1, 1]
    assert y.iloc[6] == 0                     # window 7..13 holds only 4 of the dry days
    assert y.iloc[11] == 0                    # window after the run is wet


def test_dataset_rows_stay_inside_season():
    ds = build_dataset(synthetic([2015, 2016]))
    assert ds["date"].dt.month.between(6, 9).all()
    assert (ds["date"] + pd.Timedelta(days=7) <= pd.to_datetime(ds["year"].astype(str) + "-09-30")).all()
    assert set(ds["y"].unique()) <= {0, 1}


def test_split_is_chronological_and_validates():
    tr, va, te = split_years(range(2000, 2020), n_val=3, n_test=4)
    assert max(tr) < min(va) and max(va) < min(te) and len(te) == 4
    with pytest.raises(ValueError):
        split_years(range(2000, 2005), n_val=3, n_test=3)


def test_pipeline_runs_end_to_end_and_predicts(tmp_path):
    s = synthetic(range(2000, 2016))
    ds = build_dataset(s, location_id=1)
    rep = train_and_evaluate(ds, TargetConfig(), n_val=3, n_test=4, provenance={"kind": "synthetic_test_fixture"},
                             out_dir=tmp_path, n_boot=50)
    assert rep["split_years"]["test"] == [2012, 2013, 2014, 2015]
    assert rep["test"]["brier_skill_ci"]["n_years"] == 4
    assert rep["data_provenance"]["kind"] == "synthetic_test_fixture"
    art = load_artifact(tmp_path)
    out = predict_break_risk(art, s, pd.Timestamp("2015-07-20").date())
    assert 0 <= out["probability"] <= 1 and "no weather-model forecast" in out["basis"]
    # prediction must not change if data after as_of changes
    s2 = s.copy()
    s2[s2.index > pd.Timestamp("2015-07-20")] = 0.0
    assert predict_break_risk(art, s2, pd.Timestamp("2015-07-20").date())["probability"] == out["probability"]
    with pytest.raises(InsufficientHistory):
        predict_break_risk(art, s.iloc[:10], s.index[9].date())


# ---- readiness fixes: split minimum-year boundary ----------------------------------


def test_required_years_defaults_to_split_requirement():
    assert required_years(5, 8) == 16                    # n_val + n_test + min_train(3)
    assert required_years(5, 8, min_train=13) == 26      # the planned 2000-2025 experiment


def test_split_years_exact_boundary_is_valid():
    tr, va, te = split_years(range(2000, 2016), n_val=5, n_test=8)   # exactly 16 years
    assert tr == [2000, 2001, 2002]
    assert va == [2003, 2004, 2005, 2006, 2007]
    assert te == list(range(2008, 2016))


def test_split_years_one_below_boundary_fails_clearly():
    with pytest.raises(ValueError, match="Need at least 16 years"):
        split_years(range(2000, 2015), n_val=5, n_test=8)            # only 15 years


def test_split_years_rejects_empty_split_configuration():
    for kwargs in (dict(n_val=0, n_test=8), dict(n_val=5, n_test=0), dict(n_val=5, n_test=8, min_train=0)):
        with pytest.raises(ValueError, match="must each be >= 1"):
            split_years(range(2000, 2026), **kwargs)


# ---- readiness fixes: empty validation/test rows -----------------------------------
# split_years() itself already rejects n_val/n_test < 1 (see the config test above); with valid
# configuration and enough years its year groups can never be empty. The row-level guard in
# train_and_evaluate() is defense-in-depth for splits against external year lists, so we stub
# split_years() to return years that have no rows and require a clear, deterministic failure.


def _year_frame(years):
    """Minimal dataset frame: one row per year (features unused before the guards)."""
    return pd.DataFrame({"year": list(years), "y": [i % 2 for i in range(len(years))]})


def test_split_years_year_groups_nonempty_with_valid_config():
    tr, va, te = split_years(range(2000, 2016), n_val=5, n_test=8)
    assert tr and va and te


def test_train_rejects_empty_validation_rows(monkeypatch):
    ds = _year_frame(range(2000, 2010))
    monkeypatch.setattr(mltrain, "split_years",
                        lambda years, n_val, n_test, min_train=3:
                        ([2000, 2001, 2002], [2090, 2091, 2092], [2003, 2004, 2005]))
    with pytest.raises(ValueError, match="Empty chronological split"):
        mltrain.train_and_evaluate(ds, TargetConfig(), n_val=3, n_test=3, provenance={})


def test_train_rejects_empty_test_rows(monkeypatch):
    ds = _year_frame(range(2000, 2010))
    monkeypatch.setattr(mltrain, "split_years",
                        lambda years, n_val, n_test, min_train=3:
                        ([2000, 2001, 2002], [2003, 2004, 2005], [2090, 2091, 2092]))
    with pytest.raises(ValueError, match="Empty chronological split"):
        mltrain.train_and_evaluate(ds, TargetConfig(), n_val=3, n_test=3, provenance={})


def test_train_rejects_fewer_than_three_test_years():
    ds = _year_frame(range(2000, 2010))                  # 10 years = 5+2+3 -> test has 2 years
    with pytest.raises(ValueError, match=">= 3 distinct test years"):
        train_and_evaluate(ds, TargetConfig(), n_val=5, n_test=2, provenance={})


# ---- Step 10 note: the old pooled-years CLI gate is gone by design. main() now refuses to run
# when several locations hold history and no --location-id is given, and applies the year gate to
# the selected location's own usable dataset (see the location-safe CLI tests above).


# ---- readiness fixes: year-block bootstrap minimum ---------------------------------

def test_bootstrap_bss_returns_none_below_three_test_years():
    df = pd.DataFrame({"year": [2010, 2010, 2011, 2011], "y": [0, 1, 0, 1]})
    assert bootstrap_bss(df, np.array([0.5, 0.5, 0.5, 0.5]), np.array([0.5, 0.5, 0.5, 0.5])) is None


def test_bootstrap_bss_runs_at_three_test_years():
    df = pd.DataFrame({"year": [2010, 2010, 2011, 2011, 2012, 2012], "y": [0, 1, 0, 1, 0, 1]})
    p = np.full(6, 0.5)
    ci = bootstrap_bss(df, p, p, n_boot=20)
    assert ci is not None and ci["n_years"] == 3 and ci["low"] <= ci["high"]


# ---- readiness fixes: pooled-location year gating ----------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import train_model as tm  # noqa: E402  (scripts/ CLI module; import has no side effects)


# ---- Step 10: location-safe CLI (explicit selection, multi-location guard, per-location gate) ----

LOCS = [SimpleNamespace(id=1, name="A"), SimpleNamespace(id=2, name="B")]


def _cli(monkeypatch, tmp_path, locations, series, argv, captured):
    """Wire tm.main() to in-memory fakes: no network, no database, no real training."""
    class _All:                                   # .scalars(q).all(): locations first, kinds after
        def __init__(self, items): self.items = items
        def all(self): return self.items

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def scalars(self, q):
            return _All(locations) if "locations" in str(q) else _All(["reanalysis"])

    def fake_train(ds, cfg, n_val, n_test, provenance, out_dir=None, n_boot=500, seed=0):
        captured.update(ds=ds, n_val=n_val, n_test=n_test, provenance=provenance)
        return {"selected_model": "x", "test": {"brier_skill_vs_climatology": 0.0}}

    class FakeSettings:
        models_dir = tmp_path / "models"

    def bounded(loc_id):
        """Honor the start/end window the CLI passes, like the real history_series would."""
        s = series.get(loc_id, EMPTY)
        if s.empty:
            return s
        return s[(s.index.year >= start.year) & (s.index.year <= end.year)]

    DEFAULT_START, DEFAULT_END = pd.Timestamp("1900-01-01"), pd.Timestamp("2100-12-31")
    start, end = DEFAULT_START, DEFAULT_END
    if "--start-year" in argv:
        start = pd.Timestamp(f"{int(argv[argv.index('--start-year') + 1])}-01-01")
    if "--end-year" in argv:
        end = pd.Timestamp(f"{int(argv[argv.index('--end-year') + 1])}-12-31")
    EMPTY = pd.Series(dtype=float)
    monkeypatch.setattr(sys, "argv", ["train_model.py", *argv])
    monkeypatch.setattr(tm, "session_factory", lambda: (FakeSettings(), lambda: FakeSession()))
    monkeypatch.setattr(tm, "WeatherService",
                        lambda factory, providers, settings: type("S", (), {
                            "history_series": lambda self, session, loc_id, s, e: bounded(loc_id)})())
    monkeypatch.setattr(tm, "train_and_evaluate", fake_train)


def test_cli_explicit_location_loads_only_that_location(monkeypatch, tmp_path):
    """--location-id 1 must train only on location 1 even when location 2 also has history."""
    series = {1: synthetic(range(2000, 2011), seed=1), 2: synthetic(range(2000, 2011), seed=2)}
    captured = {}
    _cli(monkeypatch, tmp_path, LOCS, series, ["--location-id", "1", "--n-val", "3", "--n-test", "3"], captured)
    assert tm.main() == 0
    assert set(captured["ds"]["location_id"].unique()) == {1}
    sel = captured["provenance"]["location_selection"]
    assert sel["mode"] == "explicit_location_id" and sel["selected_location_ids"] == [1]
    assert sel["available_location_ids_with_history"] == [1, 2]
    assert [m["location_id"] for m in captured["provenance"]["locations"]] == [1]


def test_cli_location_isolation_across_selections(monkeypatch, tmp_path):
    """Each explicit selection yields exactly one location in the dataset, hence in every split."""
    series = {1: synthetic(range(2000, 2011), seed=1), 2: synthetic(range(2000, 2011), seed=3)}
    for loc_id in (1, 2):
        captured = {}
        _cli(monkeypatch, tmp_path, LOCS, series,
             ["--location-id", str(loc_id), "--n-val", "3", "--n-test", "3"], captured)
        assert tm.main() == 0
        assert set(captured["ds"]["location_id"].unique()) == {loc_id}
        assert captured["provenance"]["locations"][0]["location_id"] == loc_id


def test_cli_rejects_multiple_locations_without_selection(monkeypatch, tmp_path, capsys):
    series = {1: synthetic(range(2000, 2011), seed=1), 2: synthetic(range(2000, 2011), seed=2)}
    captured = {}
    _cli(monkeypatch, tmp_path, LOCS, series, ["--n-val", "3", "--n-test", "3"], captured)
    assert tm.main() == 2
    err = capsys.readouterr().err
    assert "--location-id" in err and "2 locations have stored history" in err
    assert not captured                            # training must not run


def test_cli_automatic_single_location_selection(monkeypatch, tmp_path):
    series = {1: synthetic(range(2000, 2011), seed=1)}
    captured = {}
    _cli(monkeypatch, tmp_path, [LOCS[0]], series, ["--n-val", "3", "--n-test", "3"], captured)
    assert tm.main() == 0
    sel = captured["provenance"]["location_selection"]
    assert sel["mode"] == "automatic_single_location" and sel["selected_location_ids"] == [1]


def test_cli_per_location_year_gate_ignores_pooled_years(monkeypatch, tmp_path, capsys):
    """Location 1 alone lacks the 9 years the split needs; location 2's years must not rescue it
    (the pooled union has 19 years, which the old pooled gate would have accepted)."""
    series = {1: synthetic(range(2000, 2008), seed=1), 2: synthetic(range(2000, 2011), seed=2)}  # 8 vs 11 years
    captured = {}
    _cli(monkeypatch, tmp_path, LOCS, series, ["--location-id", "1", "--n-val", "3", "--n-test", "3"], captured)
    assert tm.main() == 2
    assert "has 8 usable years" in capsys.readouterr().err
    assert not captured                            # pooled years must not satisfy the gate


def test_cli_explicit_location_must_exist_and_have_history(monkeypatch, tmp_path, capsys):
    series = {1: synthetic(range(2000, 2011), seed=1)}
    captured = {}
    _cli(monkeypatch, tmp_path, LOCS, series, ["--location-id", "99"], captured)
    assert tm.main() == 2
    assert "No location with id=99" in capsys.readouterr().err
    _cli(monkeypatch, tmp_path, LOCS, series, ["--location-id", "2"], captured)
    assert tm.main() == 2
    assert "no usable stored rainfall history" in capsys.readouterr().err
    assert not captured


def test_select_history_locations_unit():
    locs = [SimpleNamespace(id=1, name="A"), SimpleNamespace(id=2, name="B")]
    hist = {1: pd.Series([1.0])}
    assert tm.select_history_locations(locs, hist, 1) == ([1], None)
    assert "No location with id=99" in tm.select_history_locations(locs, hist, 99)[1]
    assert "[1, 2]" in tm.select_history_locations(locs, hist, 99)[1]
    assert "no usable stored rainfall history" in tm.select_history_locations(locs, hist, 2)[1]
    assert "No stored history found" in tm.select_history_locations(locs, {}, None)[1]
    msg = tm.select_history_locations(locs, {1: hist[1], 2: hist[1]}, None)[1]
    assert "--location-id" in msg
    assert tm.select_history_locations(locs, hist, None) == ([1], None)


# ---- Step 10: evaluation schema (dataset/splits metadata, per-year, calibration, bootstrap provenance) ----


def test_evaluation_metadata_and_backward_compatibility(tmp_path):
    ds = build_dataset(synthetic(range(2000, 2016)), TargetConfig(), 1)   # 16 years x 101 rows
    rep = train_and_evaluate(ds, TargetConfig(), n_val=3, n_test=4, provenance={"kind": "synthetic_test_fixture"},
                             out_dir=tmp_path, n_boot=25, seed=7)
    # legacy fields retained with the same meaning
    for key in ("created_at_utc", "target", "intended_use", "data_provenance", "split_years",
                "validation_brier_by_model", "selected_model", "features", "caveats"):
        assert key in rep
    assert set(rep["test"]) >= {"model", "baseline_climatology", "baseline_dry_run_conditioned",
                                "brier_skill_vs_climatology", "brier_skill_ci"}
    assert rep["split_years"]["test"] == [2012, 2013, 2014, 2015]
    # new dataset metadata: exactly one location throughout
    assert rep["dataset"]["n_rows"] == 16 * 101 and rep["dataset"]["n_years"] == 16
    assert rep["dataset"]["n_locations"] == 1 and rep["dataset"]["location_ids"] == [1]
    assert rep["dataset"]["first_date"] == "2000-06-15" and rep["dataset"]["last_date"] == "2015-09-23"
    for name, n_rows, y0, y1 in (("train", 9 * 101, 2000, 2008), ("validation", 3 * 101, 2009, 2011),
                                 ("test", 4 * 101, 2012, 2015)):
        blk = rep["splits"][name]
        assert (blk["n_rows"], blk["n_years"], blk["year_min"], blk["year_max"]) == (n_rows, y1 - y0 + 1, y0, y1)
        assert blk["n_locations"] == 1 and blk["location_ids"] == [1]
    assert rep["model_class"] in {"Pipeline", "RandomForestClassifier"}
    ci = rep["test"]["brier_skill_ci"]
    assert (ci["resampling_unit"], ci["n_resamples"], ci["seed"], ci["confidence_level"],
            ci["interval_method"]) == ("year", 25, 7, 0.95, "percentile")
    assert len(rep["test"]["per_year"]) == 4 and len(rep["test"]["calibration"]["reliability"]) == 10
    json.dumps(rep, allow_nan=False)


def test_split_metadata_reports_multiple_locations_when_present(tmp_path):
    """The reporting layer must make a pooled dataset visible instead of hiding it
    (the CLI guard is what prevents this; the report makes it detectable)."""
    pooled = pd.concat([build_dataset(synthetic(range(2000, 2016), seed=1), TargetConfig(), 1),
                        build_dataset(synthetic(range(2000, 2016), seed=2), TargetConfig(), 2)],
                       ignore_index=True)
    rep = train_and_evaluate(pooled, TargetConfig(), n_val=3, n_test=4, provenance={})
    assert rep["dataset"]["n_locations"] == 2 and rep["dataset"]["location_ids"] == [1, 2]
    for name in ("train", "validation", "test"):
        assert rep["splits"][name]["n_locations"] == 2 and rep["splits"][name]["location_ids"] == [1, 2]


def test_per_year_metrics_and_undefined_auc():
    te = pd.DataFrame({"year": [2020] * 4 + [2021] * 4, "y": [0, 1, 0, 1, 1, 1, 1, 1]})
    p_model = np.array([0.1, 0.4, 0.35, 0.8, 0.2, 0.3, 0.4, 0.5])
    p_clim = np.array([0.25, 0.25, 0.25, 0.25, 0.6, 0.6, 0.6, 0.6])
    r20, r21 = per_year_metrics(te, p_model, p_clim)
    assert (r20["year"], r20["n"], r20["positives"], r20["negatives"]) == (2020, 4, 2, 2)
    assert r20["observed_rate"] == 0.5 and r20["roc_auc"] is not None
    assert r20["brier_skill_vs_climatology"] == pytest.approx(
        _bss(te.loc[te.year == 2020, "y"].to_numpy(float), p_model[:4], p_clim[:4]))
    assert r21["year"] == 2021 and r21["roc_auc"] is None          # single-class year -> JSON null
    assert r21["brier"] is not None and r21["log_loss"] is not None
    json.dumps(per_year_metrics(te, p_model, p_clim), allow_nan=False)


def test_per_year_bss_null_when_climatology_degenerate():
    te = pd.DataFrame({"year": [2022, 2022], "y": [1, 0]})
    rows = per_year_metrics(te, np.array([0.9, 0.1]), np.array([1.0, 0.0]))  # p_clim == y -> undefined skill
    assert rows[0]["brier_skill_vs_climatology"] is None


def test_calibration_bins_boundaries_and_empty():
    p = np.array([0.0, 0.05, 0.95, 0.95, 1.0])
    y = np.array([0.0, 0.0, 1.0, 1.0, 1.0])
    cal = calibration_diagnostics(y, p)
    assert cal["binning"] == {"n_bins": 10, "bin_width": 0.1, "interval_convention": "[low, high)",
                              "last_bin_includes_upper": True}
    rel = cal["reliability"]
    assert len(rel) == 10
    assert rel[0]["low"] == 0.0 and rel[0]["n"] == 2               # 0.0 and 0.05 land in [0, 0.1)
    assert rel[0]["mean_predicted"] == pytest.approx(0.025) and rel[0]["observed_rate"] == 0.0
    assert rel[0]["diff"] == pytest.approx(0.025)
    assert rel[1]["low"] == 0.1 and rel[1]["n"] == 0               # 0.1 belongs to the next bin, not this one
    for b in rel[1:9]:                                             # empty bins: count 0, null statistics
        assert b["n"] == 0 and b["mean_predicted"] is None
        assert b["observed_rate"] is None and b["diff"] is None
    assert rel[9]["low"] == 0.9 and rel[9]["n"] == 3               # last bin includes probability 1.0
    assert rel[9]["mean_predicted"] == pytest.approx(0.95 * 2 / 3 + 1.0 / 3)
    assert rel[9]["observed_rate"] == 1.0
    assert cal["mean_predicted"] == pytest.approx(0.59)
    assert cal["observed_rate"] == pytest.approx(0.6)
    assert cal["mean_diff"] == pytest.approx(-0.01)
    json.dumps(cal, allow_nan=False)


def test_calibration_rejects_invalid_probabilities():
    y = np.array([0.0, 1.0])
    with pytest.raises(ValueError, match="finite"):
        calibration_diagnostics(y, np.array([0.2, np.nan]))
    with pytest.raises(ValueError, match="finite"):
        calibration_diagnostics(y, np.array([0.2, np.inf]))
    with pytest.raises(ValueError, match="\\[0, 1\\]"):
        calibration_diagnostics(y, np.array([0.2, 1.5]))
    with pytest.raises(ValueError, match="\\[0, 1\\]"):
        calibration_diagnostics(y, np.array([-0.1, 0.5]))


def test_report_serializes_with_single_class_test_year(tmp_path):
    ds = build_dataset(synthetic(range(2000, 2016)), TargetConfig(), 1)
    ds.loc[ds["year"] == 2015, "y"] = 0              # force the last test year single-class
    rep = train_and_evaluate(ds, TargetConfig(), n_val=3, n_test=4, provenance={}, out_dir=tmp_path, n_boot=25)
    last = rep["test"]["per_year"][-1]
    assert last["year"] == 2015 and last["roc_auc"] is None and last["positives"] == 0
    assert rep["test"]["model"]["roc_auc"] is not None   # aggregate stays two-class via 2012-2014
    text = json.dumps(rep, allow_nan=False)          # NaN/Infinity would raise here
    assert "NaN" not in text and "Infinity" not in text


def test_bootstrap_provenance_metadata():
    df = pd.DataFrame({"year": [2010] * 4 + [2011] * 4 + [2012] * 4, "y": [0, 1, 0, 1] * 3})
    p = np.full(12, 0.5)
    ci = bootstrap_bss(df, p, p, n_boot=50, seed=11)
    assert ci["resampling_unit"] == "year" and ci["n_resamples"] == 50 and ci["seed"] == 11
    assert ci["confidence_level"] == 0.95 and ci["interval_method"] == "percentile"
    assert ci["n_years"] == 3 and "95%" in ci["method"]
    assert ci["low"] == bootstrap_bss(df, p, p, n_boot=50, seed=11)["low"]      # seed-deterministic
    assert bootstrap_bss(df, p, p)["seed"] == 0 and bootstrap_bss(df, p, p)["n_resamples"] == 500


def test_cli_rejects_min_years_below_split_requirement(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["train_model.py", "--min-years", "15"])
    with pytest.raises(SystemExit):
        tm.main()
    assert "below the 16 distinct years" in capsys.readouterr().err


# ---- Step 11: pooled multi-location training (--all-locations) and year window ------


def test_cli_all_locations_pools_every_location_with_history(monkeypatch, tmp_path):
    series = {1: synthetic(range(2000, 2011), seed=1), 2: synthetic(range(2000, 2011), seed=2)}
    captured = {}
    _cli(monkeypatch, tmp_path, LOCS, series, ["--all-locations", "--n-val", "3", "--n-test", "3"], captured)
    assert tm.main() == 0
    assert set(captured["ds"]["location_id"].unique()) == {1, 2}          # both pooled
    sel = captured["provenance"]["location_selection"]
    assert sel["mode"] == "all_locations" and sel["selected_location_ids"] == [1, 2]


def test_cli_start_end_year_restricts_dataset(monkeypatch, tmp_path):
    series = {1: synthetic(range(1995, 2011), seed=1)}
    captured = {}
    _cli(monkeypatch, tmp_path, [LOCS[0]], series,
         ["--start-year", "2000", "--end-year", "2009", "--n-val", "3", "--n-test", "3"], captured)
    assert tm.main() == 0
    yrs = set(captured["ds"]["year"].unique())
    assert yrs <= set(range(2000, 2010)) and {2008, 2009} <= yrs        # window honored at both edges


def test_cli_flags_mutually_exclusive(capsys):
    monkeypatch_argv = ["train_model.py", "--location-id", "1", "--all-locations"]
    import argparse
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--location-id", type=int)
    g.add_argument("--all-locations", action="store_true")
    with pytest.raises(SystemExit):
        ap.parse_args(monkeypatch_argv)


def test_by_location_metrics_use_same_predictions_and_baseline():
    te = pd.DataFrame({"location_id": [1] * 4 + [2] * 4, "y": [0, 1, 0, 1, 1, 1, 1, 1]})
    p_model = np.array([0.1, 0.4, 0.35, 0.8, 0.2, 0.3, 0.4, 0.5])
    p_clim = np.full(8, 0.5)
    p_dry = np.full(8, 0.25)
    rows = by_location_metrics(te, p_model, p_clim, p_dry)
    assert [r["location_id"] for r in rows] == [1, 2]
    r1 = rows[0]
    assert (r1["n"], r1["positives"], r1["negatives"]) == (4, 2, 2)
    assert r1["brier"] == pytest.approx(np.mean((p_model[:4] - te.loc[te.location_id == 1, "y"].to_numpy(float)) ** 2))
    assert r1["brier_skill_vs_climatology"] == pytest.approx(_bss(te.loc[te.location_id == 1, "y"].to_numpy(float),
                                                                   p_model[:4], p_clim[:4]))
    assert r1["brier_vs_dry_run_baseline"] == pytest.approx(
        np.mean((p_model[:4] - te.loc[te.location_id == 1, "y"].to_numpy(float)) ** 2)
        - np.mean((p_dry[:4] - te.loc[te.location_id == 1, "y"].to_numpy(float)) ** 2))
    json.dumps(rows, allow_nan=False)


def test_by_location_block_in_pooled_report(tmp_path):
    pooled = pd.concat([build_dataset(synthetic(range(2000, 2016), seed=1), TargetConfig(), 1),
                        build_dataset(synthetic(range(2000, 2016), seed=2), TargetConfig(), 2)],
                       ignore_index=True)
    rep = train_and_evaluate(pooled, TargetConfig(), n_val=3, n_test=4, provenance={}, out_dir=tmp_path)
    blocks = rep["test"]["by_location"]
    assert [b["location_id"] for b in blocks] == [1, 2]
    assert sum(b["n"] for b in blocks) == rep["test"]["model"]["n"]     # partitions the test rows
    assert all("brier_vs_dry_run_baseline" in b for b in blocks)
    json.dumps(rep, allow_nan=False)
