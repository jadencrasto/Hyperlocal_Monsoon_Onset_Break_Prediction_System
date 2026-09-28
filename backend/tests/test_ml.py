"""ML plumbing tests. The rainfall below is a synthetic TEST FIXTURE used only to check that the
pipeline runs and behaves correctly (no leakage, correct splits). It says nothing about real skill."""
import numpy as np
import pandas as pd
import pytest

from app.ml.features import FEATURES, TargetConfig, build_dataset, feature_frame, target_series
from app.ml.infer import InsufficientHistory, load_artifact, predict_break_risk
from app.ml.train import split_years, train_and_evaluate


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
