from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..analysis.monsoon import DrySpellConfig, OnsetConfig, detect_dry_spells, detect_onset
from ..ml.infer import InsufficientHistory, load_artifact, load_report, predict_break_risk
from ..models import DailyRainfall, ForecastRainfall, Location, SyncLog
from ..schemas import ForecastRefreshRequest, HistoryRefreshRequest, ModeRequest
from ..services.weather_service import SyncResult, WeatherService, utcnow

router = APIRouter()
VERSION = "0.1.0"


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
    return {"id": l.id, "name": l.name, "level": l.level, "state": l.state, "district": l.district,
            "latitude": l.latitude, "longitude": l.longitude, "coordinate_note": l.coordinate_note}


def _iso(dt: datetime | None) -> str | None:
    return dt.replace(tzinfo=timezone.utc).isoformat(timespec="seconds") if dt else None


def _sync_out(r: SyncResult) -> dict:
    return {"status": r.status, "provider": r.provider, "kind": r.kind, "n_records": r.n_records,
            "message": r.message, "finished_at": _iso(r.finished_at)}


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
    return {"status": "ok", "version": VERSION, "database": "ok", "mode_preference": pref,
            "effective_mode": svc.effective_mode(pref),
            "model_available": load_artifact(svc.settings.models_dir) is not None,
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
    q = select(Location).order_by(Location.state, Location.name)
    if level:
        q = q.where(Location.level == level)
    if state:
        q = q.where(Location.state == state)
    return [_loc_out(l) for l in session.scalars(q)]


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
    _loc(session, location_id)
    cfg = OnsetConfig()
    res = detect_onset(_year_series(svc, session, location_id, year), year, cfg)
    return {"location_id": location_id, "year": year, "type": "historical_analysis", "status": res.status,
            "onset_date": res.onset_date.isoformat() if res.onset_date else None,
            "detail": res.detail, "config": cfg.__dict__}


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


@router.get("/model/evaluation")
def model_evaluation(svc: WeatherService = Depends(service)):
    rep = load_report(svc.settings.models_dir)
    if rep is None:
        raise HTTPException(404, "No evaluation report. Train a model with scripts/train_model.py.")
    return rep


# ---- sources & sync ----------------------------------------------------------------
@router.get("/sources")
def sources(session: Session = Depends(get_session), svc: WeatherService = Depends(service)):
    out = []
    for name, prov in svc.providers.items():
        last_ok = session.scalar(select(func.max(SyncLog.finished_at)).where(SyncLog.provider == name, SyncLog.status == "ok"))
        last_err = session.execute(select(SyncLog).where(SyncLog.provider == name, SyncLog.status == "error")
                                   .order_by(SyncLog.id.desc()).limit(1)).scalar_one_or_none()
        out.append({**prov.info.__dict__, "last_success": _iso(last_ok),
                    "last_error": {"at": _iso(last_err.finished_at), "message": last_err.message} if last_err else None,
                    "cached_history_rows": session.scalar(select(func.count()).select_from(DailyRainfall).where(DailyRainfall.provider == name)),
                    "cached_forecast_rows": session.scalar(select(func.count()).select_from(ForecastRainfall).where(ForecastRainfall.provider == name))})
    return {"providers": out,
            "not_integrated": ["IMD", "CHIRPS", "ERA5 (direct)", "ECMWF S2S"],
            "note": "See docs/DATA_SOURCES.md for why each is not integrated yet."}


@router.get("/sync-log")
def sync_log(limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)):
    rows = session.scalars(select(SyncLog).order_by(SyncLog.id.desc()).limit(limit)).all()
    return [{"id": r.id, "location_id": r.location_id, "provider": r.provider, "kind": r.kind,
             "status": r.status, "n_records": r.n_records, "message": r.message,
             "finished_at": _iso(r.finished_at)} for r in rows]
