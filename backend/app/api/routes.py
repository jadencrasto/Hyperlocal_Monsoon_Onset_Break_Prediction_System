from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..analysis.monsoon import DrySpellConfig, OnsetConfig, detect_dry_spells, detect_onset
from ..ml.infer import InsufficientHistory, load_artifact, load_report, predict_break_risk
from ..ml.spatial import spatial_awareness_status
from ..models import DailyRainfall, ForecastRainfall, Location, SyncLog
from ..schemas import ForecastRefreshRequest, HistoryRefreshRequest, ModeRequest
from ..services import location_service as ls
from ..services.data_quality import coverage_summary, validate_forecast_freshness, validate_location_data
from ..services.location_service import HierarchyError
from ..services.weather_service import SyncResult, WeatherService, utcnow

router = APIRouter()
VERSION = "0.2.0"


def get_session(request: Request):
    with request.app.state.session_factory() as s:
        yield s


def service(request: Request) -> WeatherService:
    return request.app.state.service


def _loc(session: Session, location_id: int) -> Location:
    loc = session.get(Location, location_id)
    if loc is None:
        raise HTTPException(404, f"Location {location_id} not found")
    return loc


def _loc_out(l: Location) -> dict:
    return {"id": l.id, "name": l.name, "level": l.level, "parent_id": l.parent_id,
            "state": l.state, "district": l.district,
            "latitude": l.latitude, "longitude": l.longitude, "coordinate_note": l.coordinate_note}


def _iso(dt: datetime | None) -> str | None:
    return dt.replace(tzinfo=timezone.utc).isoformat(timespec="seconds") if dt else None


def _sync_out(r: SyncResult) -> dict:
    return {"status": r.status, "provider": r.provider, "kind": r.kind, "n_records": r.n_records,
            "message": r.message, "finished_at": _iso(r.finished_at), "category": r.category}


def _raise_for_sync(r: SyncResult):
    if r.status == "error":
        raise HTTPException(502, detail={"error": "provider_failure", **_sync_out(r)})
    if r.status == "skipped_offline":
        raise HTTPException(409, detail={"error": "offline", **_sync_out(r)})


# ---- status -----------------------------------------------------------------------
@router.get("/health")
def health(request: Request, session: Session = Depends(get_session), svc: WeatherService = Depends(service)):
    session.execute(text("select 1"))
    pref = request.app.state.mode_pref
    effective = svc.effective_mode(pref)
    internet = svc.is_online()
    # Actual operating state: not just configured mode but real data/provider status
    if effective == "online" and not internet:
        actual_state = "degraded_offline"
    else:
        actual_state = effective
    spatial = spatial_awareness_status()
    return {"status": "ok", "version": VERSION, "database": "ok", "mode_preference": pref,
            "effective_mode": effective,
            "actual_operating_state": actual_state,
            "internet_reachable": internet,
            "model_available": load_artifact(svc.settings.models_dir) is not None,
            "spatial_awareness": spatial["is_spatially_aware"],
            "geographic_scope": {
                "current": "district_hq_coordinate_points",
                "target": "block_village_target_coordinates",
                "note": "Current predictions use district-HQ approximate coordinates. "
                        "Block/village-level data is not yet available."
            },
            "time_utc": _iso(utcnow())}


@router.get("/mode")
def get_mode(request: Request, svc: WeatherService = Depends(service)):
    pref = request.app.state.mode_pref
    return {"preference": pref, "effective": svc.effective_mode(pref), "internet_reachable": svc.is_online()}


@router.put("/mode")
def set_mode(body: ModeRequest, request: Request, svc: WeatherService = Depends(service)):
    request.app.state.mode_pref = body.preference
    return {"preference": body.preference, "effective": svc.effective_mode(body.preference)}


# ---- locations ---------------------------------------------------------------------
@router.get("/locations")
def locations(level: str | None = None, state: str | None = None, session: Session = Depends(get_session)):
    try:
        return ls.list_locations(session, level=level, state=state)
    except HierarchyError as exc:
        raise HTTPException(422, detail={"error": "invalid_level", "hint": str(exc)}) from exc


@router.get("/locations/tree")
def location_tree(session: Session = Depends(get_session)):
    """Full State -> District -> Block -> Panchayat hierarchy for navigation (Step 16 map).
    Each node carries n_children, has_data, and nested children where present."""
    return ls.tree(session)


@router.get("/locations/{location_id}/children")
def location_children(location_id: int, session: Session = Depends(get_session)):
    try:
        return ls.children_of(session, location_id)
    except HierarchyError as exc:
        raise HTTPException(404, detail={"error": "location_not_found", "hint": str(exc)}) from exc


@router.get("/locations/{location_id}/coverage")
def location_coverage(location_id: int, session: Session = Depends(get_session)):
    """Rainfall data availability for a node or its descendant districts."""
    try:
        return ls.rainfall_coverage(session, location_id)
    except HierarchyError as exc:
        raise HTTPException(404, detail={"error": "location_not_found", "hint": str(exc)}) from exc


@router.get("/locations/{location_id}")
def location_detail(location_id: int, session: Session = Depends(get_session)):
    return _loc_out(_loc(session, location_id))


# ---- history & weather -------------------------------------------------------------
@router.get("/locations/{location_id}/history")
def history(location_id: int, start: date, end: date, session: Session = Depends(get_session)):
    _loc(session, location_id)
    if start > end:
        raise HTTPException(422, "start must be on or before end")
    if (end - start).days > 366 * 45:
        raise HTTPException(422, "date range too large")
    rows = session.scalars(select(DailyRainfall).where(
        DailyRainfall.location_id == location_id, DailyRainfall.date.between(start, end))
        .order_by(DailyRainfall.date)).all()
    return {"location_id": location_id, "unit": "mm/day",
            "note": "kind='reanalysis' is model-derived (e.g. ERA5), not a gauge observation.",
            "records": [{"date": r.date.isoformat(), "precip_mm": r.precip_mm, "kind": r.kind,
                         "provider": r.provider, "fetched_at": _iso(r.fetched_at)} for r in rows]}


@router.post("/locations/{location_id}/history/refresh")
def history_refresh(location_id: int, body: HistoryRefreshRequest, request: Request,
                    session: Session = Depends(get_session), svc: WeatherService = Depends(service)):
    loc = _loc(session, location_id)
    try:
        res = svc.refresh_history(session, loc, body.provider, body.start, body.end, request.app.state.mode_pref)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    _raise_for_sync(res)
    return _sync_out(res)


@router.get("/locations/{location_id}/forecast")
def forecast(location_id: int, provider: str | None = None, session: Session = Depends(get_session),
             svc: WeatherService = Depends(service)):
    _loc(session, location_id)
    snap = svc.latest_forecast(session, location_id, provider)
    if snap is None:
        raise HTTPException(404, "No cached forecast for this location. Refresh while online.")
    info = svc.providers.get(snap.provider)
    return {"location_id": location_id, "type": "third_party_forecast", "provider": snap.provider,
            "retrieved_at": _iso(snap.retrieved_at), "age_hours": round(snap.age_hours, 2),
            "freshness": "stale" if snap.stale else "fresh",
            "stale_after_hours": svc.settings.forecast_stale_hours,
            "spatial_note": info.info.spatial_note if info else None,
            "label": ("STALE cached forecast - not current" if snap.stale else "Cached forecast, within freshness window"),
            "records": [{"date": d.isoformat(), "precip_mm": v} for d, v in snap.records]}


@router.post("/locations/{location_id}/forecast/refresh")
def forecast_refresh(location_id: int, body: ForecastRefreshRequest, request: Request,
                     session: Session = Depends(get_session), svc: WeatherService = Depends(service)):
    loc = _loc(session, location_id)
    try:
        res = svc.refresh_forecast(session, loc, body.provider, request.app.state.mode_pref)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    _raise_for_sync(res)
    return _sync_out(res)


# ---- monsoon analysis --------------------------------------------------------------
def _year_series(svc, session, location_id, year, tail_days=60):
    start, end = date(year, 4, 1), date(year, 10, 31)
    return svc.history_series(session, location_id, start, end)


@router.get("/locations/{location_id}/monsoon/onset")
def onset(location_id: int, year: int = Query(ge=1940, le=2100), session: Session = Depends(get_session),
          svc: WeatherService = Depends(service)):
    """Retrospective monsoon onset DETECTION from stored historical rainfall.

    This is observed/historical onset detection (type A), NOT future onset prediction.
    It analyses past rainfall data to identify when monsoon onset occurred in a given year.
    For future onset prediction (type B), see /monsoon/onset-prediction (not yet implemented).
    """
    _loc(session, location_id)
    cfg = OnsetConfig()
    res = detect_onset(_year_series(svc, session, location_id, year), year, cfg)
    return {"location_id": location_id, "year": year,
            "type": "observed_onset_detection",
            "analysis_kind": "retrospective",
            "status": res.status,
            "observed_onset": res.onset_date.isoformat() if res.onset_date else None,
            # Backward compat: keep onset_date for existing consumers
            "onset_date": res.onset_date.isoformat() if res.onset_date else None,
            "detail": res.detail, "config": cfg.__dict__,
            "note": "This is retrospective onset detection from historical rainfall, "
                    "not a future onset prediction. See /monsoon/onset-prediction."}


@router.get("/locations/{location_id}/monsoon/dry-spells")
def dry_spells(location_id: int, year: int = Query(ge=1940, le=2100), after_onset: bool = False,
               session: Session = Depends(get_session), svc: WeatherService = Depends(service)):
    _loc(session, location_id)
    s = _year_series(svc, session, location_id, year)
    onset_date = detect_onset(s, year).onset_date if after_onset else None
    cfg = DrySpellConfig()
    spells = detect_dry_spells(s, year, cfg, onset_date)
    return {"location_id": location_id, "year": year, "type": "historical_analysis",
            "note": "Local rainfall dry spells, not official meteorological monsoon breaks.",
            "config": cfg.__dict__, "onset_date": onset_date.isoformat() if onset_date else None,
            "spells": [{"start": sp.start.isoformat(), "end": sp.end.isoformat(), "length_days": sp.length,
                        "total_mm": round(sp.total_mm, 2), "ended_by": sp.ended_by, "scope": sp.scope,
                        "resumption_date": sp.resumption_date.isoformat() if sp.resumption_date else None}
                       for sp in spells]}


@router.get("/locations/{location_id}/monsoon/break-risk")
def break_risk(location_id: int, as_of: date | None = None, session: Session = Depends(get_session),
               svc: WeatherService = Depends(service)):
    """Works offline: needs only the local model artifact and locally stored rainfall history."""
    _loc(session, location_id)
    art = load_artifact(svc.settings.models_dir)
    if art is None:
        raise HTTPException(503, "No trained model found. Run scripts/train_model.py first.")
    latest = session.scalar(select(func.max(DailyRainfall.date)).where(DailyRainfall.location_id == location_id))
    if latest is None:
        raise HTTPException(404, "No stored rainfall history for this location. Run the data download first.")
    as_of = as_of or latest
    series = svc.history_series(session, location_id, date(1900, 1, 1), as_of)
    try:
        out = predict_break_risk(art, series, as_of)
    except InsufficientHistory as exc:
        raise HTTPException(422, str(exc)) from exc
    rep = load_report(svc.settings.models_dir) or {}
    return {**out, "type": "own_model_prediction", "data_age_days": (date.today() - as_of).days,
            "training_data": rep.get("data_provenance"),
            "test_brier_skill_vs_climatology": (rep.get("test") or {}).get("brier_skill_vs_climatology")}


# ---- Step 13/14: demo prediction endpoint ------------------------------------------
SCHEMA_VERSION = "1.0"


def _risk_category(p: float) -> str:
    """Demo categorization of a probability into three operational bands.
    NOT calibrated decision thresholds - the model is not calibrated (Step 11)."""
    return "low" if p < 0.2 else "moderate" if p < 0.4 else "high"


def _evidence_level(test: dict) -> str:
    """Mechanical, honest label of what the evaluation established - no percentages."""
    ci = test.get("brier_skill_ci") or {}
    skill = test.get("brier_skill_vs_climatology")
    if skill is None:
        return "no_evaluation_available"
    beats_climatology = isinstance(ci.get("low"), (int, float)) and ci["low"] > 0
    model_brier = (test.get("model") or {}).get("brier")
    dry_brier = (test.get("baseline_dry_run_conditioned") or {}).get("brier")
    beats_heuristic = (isinstance(model_brier, (int, float)) and isinstance(dry_brier, (int, float))
                       and model_brier < dry_brier)
    if beats_climatology and beats_heuristic:
        return "positive_skill_vs_climatology_and_heuristic"
    if beats_climatology:
        return "modest_positive_skill_vs_climatology_only"
    return "no_skill_demonstrated"


def _uncertainty_block(test: dict, rep: dict, data_age_days: int) -> dict:
    """Uncertainty metadata strictly limited to what the evaluation supports.

    The pipeline produces a point probability per day; it has NO per-prediction interval
    (that would need a quantile/conformal method the current training never ran), so that
    field is explicitly null instead of invented. What DOES exist:
      * population-level skill + year-block bootstrap CI (uncertainty over test YEARS,
        not per day),
      * the calibration diagnostic (systematic over/under-prediction),
      * per-year skill spread (how stable skill was across the 8 test years)."""
    per_year = test.get("per_year") or []
    bss_values = [r.get("brier_skill_vs_climatology") for r in per_year
                  if isinstance(r.get("brier_skill_vs_climatology"), (int, float))]
    cal = test.get("calibration") or {}
    mean_diff = cal.get("mean_diff")
    ci = test.get("brier_skill_ci") or {}
    return {
        "individual_prediction_interval": {"available": False,
            "reason": "The current pipeline fits a single point-probability model; no quantile, "
                      "ensemble or conformal method was trained, so no statistically justified "
                      "per-prediction interval exists. null means 'not provided', not zero."},
        "evaluation_skill": {
            "brier_skill_vs_climatology": test.get("brier_skill_vs_climatology"),
            "brier_skill_ci": ci,
            "ci_interpretation": "95% year-block bootstrap over the 8 test years - population-level "
                                "skill uncertainty, NOT an interval around this prediction",
            "n_test_years": ci.get("n_years") or (len(per_year) or None),
        },
        "calibration": {
            "mean_predicted": cal.get("mean_predicted"), "observed_rate": cal.get("observed_rate"),
            "mean_diff": mean_diff,
            "interpretation": ("model over-predicts event probability on average" if
                               (isinstance(mean_diff, (int, float)) and mean_diff > 0) else
                               "model under-predicts event probability on average" if
                               (isinstance(mean_diff, (int, float)) and mean_diff < 0) else None),
            "note": cal.get("note"),
        },
        "per_year_stability": {
            "n_years": len(bss_values) or None,
            "bss_min": min(bss_values) if bss_values else None,
            "bss_max": max(bss_values) if bss_values else None,
            "negative_years": sum(1 for v in bss_values if v < 0) or 0,
            "note": "spread of per-year skill across test years; wide spread means skill is "
                    "not year-stable" if bss_values else None,
        },
        "evidence_level": _evidence_level(test),
        "data_caveats": {
            "freshness": "current" if data_age_days <= 2 else ("recent" if data_age_days <= 7 else "stale"),
            "data_age_days": data_age_days,
            "note": "staleness lowers trust in the input features but is not quantifiable as "
                    "probability without assumptions the pipeline does not make",
        },
    }


@router.get("/locations/{location_id}/prediction/break-risk")
def prediction_break_risk(location_id: int, request: Request, as_of: date | None = None,
                          session: Session = Depends(get_session),
                          svc: WeatherService = Depends(service)):
    """Frontend-ready break-risk prediction for a pilot location.

    Supports automatic Online -> Offline fallback (Requirement 28):
    ONLINE: Try live data -> Success -> update local cache -> prediction.
    Failure / Offline: Check local cache -> Offline prediction if valid.
    """
    location = _loc(session, location_id)
    art = load_artifact(svc.settings.models_dir)
    if art is None:
        raise HTTPException(503, detail={"error": "model_unavailable",
                            "hint": "Run scripts/train_model.py first."})

    mode = svc.effective_mode(request.app.state.mode_pref)
    is_live = False

    # Requirement 28: Automatic Online -> Offline fallback flow
    if mode == "online" and as_of is None:
        live_ok, _ = svc.try_online_refresh(session, location)
        if live_ok:
            is_live = True

    latest = session.scalar(select(func.max(DailyRainfall.date)).where(
        DailyRainfall.location_id == location_id))
    if latest is None:
        raise HTTPException(404, detail={"error": "no_stored_history",
                            "hint": "Run scripts/download_history.py first."})
    if as_of is None:
        as_of = latest
    if as_of > date.today():
        raise HTTPException(422, detail={"error": "future_date",
                            "hint": "No rainfall exists beyond today; predictions for future "
                                    "dates would be fabricated."})
    if not (date(as_of.year, 6, 15) <= as_of <= date(as_of.year, 9, 30)):
        raise HTTPException(422, detail={"error": "out_of_season",
                            "hint": "The model is defined only inside the monsoon season "
                                    "(Jun 15 - Sep 30); off-season predictions would be "
                                    "extrapolation beyond the training domain."})

    data_age_days = (date.today() - as_of).days
    # Requirement 27: If cached data is too old for prediction, reject cleanly
    if not is_live and (as_of == latest) and (data_age_days > svc.settings.max_cache_age_days):
        raise HTTPException(422, detail={"error": "cached_data_too_old",
                            "hint": f"Cached rainfall data is too old ({data_age_days} days old, max allowed {svc.settings.max_cache_age_days} days). Prediction unavailable."})

    series = svc.history_series(session, location_id, date(1900, 1, 1), as_of)
    try:
        out = predict_break_risk(art, series, as_of)
    except InsufficientHistory as exc:
        raise HTTPException(422, detail={"error": "insufficient_or_gappy_history",
                                          "hint": str(exc)}) from exc
    rep = load_report(svc.settings.models_dir) or {}
    test = rep.get("test") or {}
    prov = rep.get("data_provenance") or {}
    sel = prov.get("location_selection") or {}
    ds = rep.get("dataset") or {}

    last_row = session.execute(
        select(DailyRainfall.provider, DailyRainfall.fetched_at).where(DailyRainfall.location_id == location_id)
        .order_by(DailyRainfall.date.desc(), DailyRainfall.fetched_at.desc()).limit(1)
    ).first()
    last_provider = last_row[0] if last_row else None
    last_fetched_at = last_row[1] if last_row else None
    update_age_s = (utcnow() - last_fetched_at).total_seconds() if last_fetched_at else None

    cache_status = "live" if is_live else ("offline" if mode == "offline" else "cached")

    return {
        "type": "break_risk_prediction",
        "schema_version": SCHEMA_VERSION,
        "location": _loc_out(location),
        "prediction_date": as_of.isoformat(),
        "probability": out["probability"],
        "risk_category": _risk_category(out["probability"]),
        "risk_bands": {"low": "< 0.2", "moderate": "0.2 to < 0.4", "high": ">= 0.4",
                       "note": "presentation bands for the demo UI, NOT calibrated decision "
                               "thresholds - see uncertainty.calibration"},
        "horizon_days": out["horizon_days"],
        "event": out["event"],
        "basis": out["basis"],
        "last_sync_failure": _last_sync_failure(session, location_id),
        "model": {
            "name": out["model"],
            "class": rep.get("model_class"),
            "trained_on_locations": sel.get("selected_location_ids"),
            "trained_period": {"first_date": ds.get("first_date"), "last_date": ds.get("last_date"),
                               "n_years": ds.get("n_years")},
            "trained_through": ds.get("last_date"),
            "test_skill": {"brier_skill_vs_climatology": test.get("brier_skill_vs_climatology"),
                           "brier_skill_ci": test.get("brier_skill_ci")},
            "baselines": {"model_brier": (test.get("model") or {}).get("brier"),
                          "climatology_brier": (test.get("baseline_climatology") or {}).get("brier"),
                          "dry_run_baseline_brier": (test.get("baseline_dry_run_conditioned") or {}).get("brier")},
            "intended_use": rep.get("intended_use"),
            "caveats": rep.get("caveats"),
        },
        "uncertainty": _uncertainty_block(test, rep, data_age_days),
        "data_status": {
            "source": "stored_reanalysis_history",
            "provider": last_provider,
            "latest_rainfall_date": latest.isoformat(),
            "data_age_days": data_age_days,
            "freshness": "current" if data_age_days <= 2 else ("recent" if data_age_days <= 7 else "stale"),
            "input_days_used": int(series.index.size),
            "input_completeness": round(float(series.notna().all()) if len(series) else 0.0, 3),
            "cache_status": cache_status,
            "data_source": "live" if is_live else "cache",
            "is_live": is_live,
            "last_updated": _iso(last_fetched_at),
            "update_age_seconds": round(update_age_s, 1) if update_age_s is not None else None,
        },
        "limitations": [
            "Historical-pattern-based estimate from past rainfall only - NOT a weather forecast.",
            "Not operationally validated; test skill on reanalysis data may not transfer to gauge "
            "observations or future seasons.",
            "Skill is modest and does not demonstrate value over the simple dry-run heuristic "
            "(see /api/model/evaluation).",
            "risk_category uses fixed presentation bands, not calibrated decision thresholds.",
            "Per-year performance varies; treat the probability as one input among several, "
            "not an actionable forecast.",
        ],
    }


@router.get("/model/evaluation")
def model_evaluation(svc: WeatherService = Depends(service)):
    rep = load_report(svc.settings.models_dir)
    if rep is None:
        raise HTTPException(404, "No evaluation report. Train a model with scripts/train_model.py.")
    return rep


# ---- onset prediction (not implemented) -------------------------------------------
@router.get("/locations/{location_id}/monsoon/onset-prediction")
def onset_prediction(location_id: int, session: Session = Depends(get_session)):
    """Future monsoon onset prediction — NOT YET IMPLEMENTED.

    This endpoint is reserved for genuine future onset prediction (type B).
    The existing /monsoon/onset endpoint provides retrospective onset detection (type A)
    from historical data. This endpoint will provide forward-looking predictions when
    the required forecast-driven model is implemented.
    """
    _loc(session, location_id)
    return {
        "location_id": location_id,
        "type": "onset_prediction",
        "prediction_status": "not_implemented",
        "predicted_onset": None,
        "confidence": None,
        "observed_onset": None,
        "note": "Future onset prediction is not yet implemented. "
                "Use /monsoon/onset?year=YYYY for retrospective onset detection "
                "from historical rainfall data.",
        "requirements": [
            "Forecast-driven model (e.g. ECMWF S2S reforecast archive)",
            "Calibrated probability estimates for onset timing",
            "Validation against historical observed onsets",
        ],
    }


# ---- forecast contract -------------------------------------------------------------
@router.get("/locations/{location_id}/forecast/status")
def forecast_status(location_id: int, session: Session = Depends(get_session),
                    svc: WeatherService = Depends(service)):
    """Forecast data status and readiness for prediction integration.

    Reports what forecast data is available, its freshness, and whether it
    could participate in prediction (currently: forecast is NOT used by the
    ML model, which uses only historical rainfall).
    """
    _loc(session, location_id)
    freshness = validate_forecast_freshness(session, location_id, svc.settings.forecast_stale_hours)
    snap = svc.latest_forecast(session, location_id)

    forecast_records = []
    if snap:
        forecast_records = [{"date": d.isoformat(), "precip_mm": v} for d, v in snap.records]

    return {
        "location_id": location_id,
        "forecast_available": snap is not None,
        "freshness": freshness,
        "n_forecast_days": len(forecast_records) if snap else 0,
        "prediction_integration": {
            "integrated": False,
            "reason": "The current ML model uses only historical rainfall features. "
                      "Third-party forecast data is displayed separately but does NOT "
                      "feed into the break-risk prediction model.",
            "required_for_integration": [
                "Forecast-based features in the ML pipeline",
                "Reforecast archive for training (e.g. ECMWF S2S)",
                "Validation showing forecast features improve skill",
            ],
        },
        "provider_info": {
            "name": snap.provider if snap else None,
            "retrieved_at": _iso(snap.retrieved_at) if snap else None,
            "age_hours": round(snap.age_hours, 2) if snap else None,
            "stale": snap.stale if snap else None,
        },
        "offline_usable": snap is not None,
        "offline_note": "Cached forecast data can be served offline but will become stale. "
                        "Stale forecasts are labelled but not suppressed.",
    }


# ---- data quality ------------------------------------------------------------------
@router.get("/locations/{location_id}/data-quality")
def data_quality(location_id: int, session: Session = Depends(get_session),
                 svc: WeatherService = Depends(service)):
    """Data quality assessment for a location's stored rainfall history."""
    _loc(session, location_id)
    report = validate_location_data(session, location_id,
                                     max_age_days=svc.settings.max_cache_age_days)
    return {
        "location_id": report.location_id,
        "status": report.status,
        "issues": report.issues,
        "total_records": report.total_records,
        "first_date": report.first_date.isoformat() if report.first_date else None,
        "last_date": report.last_date.isoformat() if report.last_date else None,
        "expected_days": report.expected_days,
        "actual_days": report.actual_days,
        "missing_days": report.missing_days,
        "duplicate_count": report.duplicate_count,
        "null_precip_count": report.null_precip_count,
        "impossible_values": report.impossible_values,
        "continuity_ratio": round(report.continuity_ratio, 4) if report.continuity_ratio is not None else None,
        "providers": report.providers,
        "kinds": report.kinds,
    }


@router.get("/data-quality/coverage")
def data_coverage(session: Session = Depends(get_session)):
    """Overview of data coverage across all district locations."""
    return coverage_summary(session)


# ---- spatial ML status -------------------------------------------------------------
@router.get("/model/spatial-status")
def model_spatial_status():
    """Current spatial awareness status of the ML model.

    Reports whether the model includes location/spatial features, and lists
    candidate approaches for future spatial modeling experiments.
    """
    return spatial_awareness_status()


# ---- sources & sync ----------------------------------------------------------------
def _split_category(message: str | None) -> tuple[str | None, str | None]:
    """Split the Step 25 `[category: x]` tag off a sync-log message.
    Returns (category, clean_message)."""
    if message and message.startswith("[category: "):
        tag, _, rest = message.partition("]")
        return (tag.removeprefix("[category: ") or None), rest.strip()
    return None, message


def _last_sync_failure(session: Session, location_id: int) -> dict | None:
    """Most recent failed refresh for this location within the last 24h (Step 25 fallback
    signal). Null after 24h or when everything is healthy — cached data stays usable."""
    cutoff = utcnow() - timedelta(hours=24)
    row = session.scalar(select(SyncLog).where(
        SyncLog.location_id == location_id, SyncLog.status == "error",
        SyncLog.finished_at >= cutoff).order_by(SyncLog.id.desc()).limit(1))
    if row is None:
        return None
    last_ok = session.scalar(select(func.max(SyncLog.finished_at)).where(
        SyncLog.location_id == location_id, SyncLog.status == "ok", SyncLog.kind == row.kind))
    if last_ok and last_ok >= row.finished_at:
        return None
    category, message = _split_category(row.message)
    return {"kind": row.kind, "provider": row.provider, "category": category,
            "message": message, "finished_at": _iso(row.finished_at)}


@router.get("/sources")
def sources(session: Session = Depends(get_session), svc: WeatherService = Depends(service)):
    out = []
    for name, prov in svc.providers.items():
        last_ok = session.scalar(select(func.max(SyncLog.finished_at)).where(SyncLog.provider == name, SyncLog.status == "ok"))
        last_err = session.execute(select(SyncLog).where(SyncLog.provider == name, SyncLog.status == "error")
                                   .order_by(SyncLog.id.desc()).limit(1)).scalar_one_or_none()
        err_category, err_message = _split_category(last_err.message if last_err else None)
        out.append({**prov.info.__dict__, "last_success": _iso(last_ok),
                    "last_error": {"at": _iso(last_err.finished_at),
                                   "message": err_message, "category": err_category} if last_err else None,
                    "cached_history_rows": session.scalar(select(func.count()).select_from(DailyRainfall).where(DailyRainfall.provider == name)),
                    "cached_forecast_rows": session.scalar(select(func.count()).select_from(ForecastRainfall).where(ForecastRainfall.provider == name))})
    return {"providers": out,
            "not_integrated": ["IMD", "CHIRPS", "ERA5 (direct)", "ECMWF S2S"],
            "note": "See docs/DATA_SOURCES.md for why each is not integrated yet."}


@router.get("/sync-log")
def sync_log(limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)):
    rows = session.scalars(select(SyncLog).order_by(SyncLog.id.desc()).limit(limit)).all()
    out = []
    for r in rows:
        category, message = _split_category(r.message)
        out.append({"id": r.id, "location_id": r.location_id, "provider": r.provider, "kind": r.kind,
                    "status": r.status, "n_records": r.n_records, "message": message,
                    "category": category, "finished_at": _iso(r.finished_at)})
    return out
