"""
Patient endpoints

GET /patients                          List all patients
GET /patients/<id>                     Demographics
GET /patients/<id>/summary             Pre-visit brief (primary endpoint)
GET /patients/<id>/conditions          Condition list
GET /patients/<id>/medications         Medication list
GET /patients/<id>/observations        All observations, newest first
GET /patients/<id>/observations/latest Latest per LOINC code
GET /patients/<id>/observations/trend/<loinc_code>  Time series for one metric
GET /patients/<id>/procedures          Procedure history
GET /patients/<id>/alerts              Clinical alert flags
"""

from flask import Blueprint, jsonify, request, abort
import app.store as store
from app.fhir import fmt_patient, fmt_condition, fmt_medication, fmt_observation, fmt_procedure
from app.alerts import get_alerts

bp = Blueprint("patients", __name__)


def _get_patient_or_404(patient_id: str) -> dict:
    patient = store.get_patient(patient_id)
    if not patient:
        abort(404, description=f"Patient '{patient_id}' not found")
    return patient


@bp.get("/patients")
def list_patients():
    patients = [fmt_patient(p) for p in store.get_all_patients()]
    return jsonify({"total": len(patients), "patients": patients})


@bp.get("/patients/<patient_id>")
def get_patient(patient_id):
    return jsonify(fmt_patient(_get_patient_or_404(patient_id)))


@bp.get("/patients/<patient_id>/summary")
def get_summary(patient_id):
    """Pre-visit brief — everything a clinician needs before the exam room."""
    p = _get_patient_or_404(patient_id)
    pid = patient_id.lower()

    alerts = get_alerts(pid)
    conditions = [fmt_condition(c) for c in store.active_conditions(pid)]
    medications = [fmt_medication(m) for m in store.active_medications(pid)]
    vitals = [fmt_observation(o) for o in store.latest_observations(pid)]

    # Trends only make sense with 2+ data points
    hba1c_trend = [
        {"value": o["value"], "unit": o["unit"], "date": o["effective_date"]}
        for o in store.observation_trend(pid, "4548-4")
    ]
    bp_rows = store.bp_trend(pid)
    bp_trend = [
        {"systolic": r["systolic"], "diastolic": r["diastolic"], "unit": "mmHg", "date": r["date"]}
        for r in bp_rows
    ]

    trends = {}
    if len(hba1c_trend) >= 2:
        trends["hba1c"] = hba1c_trend
    if len(bp_trend) >= 2:
        trends["blood_pressure"] = bp_trend

    return jsonify({
        "patient": fmt_patient(p),
        "alerts": {
            "count":        len(alerts),
            "has_critical": any(a["severity"] == "critical" for a in alerts),
            "items":        alerts,
        },
        "active_conditions":  conditions,
        "active_medications": medications,
        "latest_vitals_labs": vitals,
        "recent_procedures":  [fmt_procedure(pr) for pr in store.procedures(pid)[:5]],
        "trends":             trends,
    })


@bp.get("/patients/<patient_id>/conditions")
def get_conditions(patient_id):
    _get_patient_or_404(patient_id)
    status_filter = request.args.get("status")
    formatted = [fmt_condition(c) for c in store.all_conditions(patient_id.lower())]
    if status_filter:
        formatted = [c for c in formatted if c["clinical_status"] == status_filter]
    return jsonify({"patient_id": patient_id.lower(), "total": len(formatted), "conditions": formatted})


@bp.get("/patients/<patient_id>/medications")
def get_medications(patient_id):
    _get_patient_or_404(patient_id)
    meds = [fmt_medication(m) for m in store.active_medications(patient_id.lower())]
    return jsonify({"patient_id": patient_id.lower(), "total": len(meds), "medications": meds})


@bp.get("/patients/<patient_id>/observations")
def get_observations(patient_id):
    _get_patient_or_404(patient_id)
    obs = [fmt_observation(o) for o in store.observations(patient_id.lower())]
    return jsonify({"patient_id": patient_id.lower(), "total": len(obs), "observations": obs})


@bp.get("/patients/<patient_id>/observations/latest")
def get_latest_observations(patient_id):
    _get_patient_or_404(patient_id)
    obs = [fmt_observation(o) for o in store.latest_observations(patient_id.lower())]
    return jsonify({"patient_id": patient_id.lower(), "total": len(obs), "observations": obs})


@bp.get("/patients/<patient_id>/observations/trend/<loinc_code>")
def get_observation_trend(patient_id, loinc_code):
    _get_patient_or_404(patient_id)
    series = [
        {"value": o["value"], "unit": o["unit"], "date": o["effective_date"], "status": o["status"]}
        for o in store.observation_trend(patient_id.lower(), loinc_code)
    ]
    return jsonify({"patient_id": patient_id.lower(), "loinc_code": loinc_code,
                    "total": len(series), "series": series})


@bp.get("/patients/<patient_id>/procedures")
def get_procedures(patient_id):
    _get_patient_or_404(patient_id)
    procs = [fmt_procedure(pr) for pr in store.procedures(patient_id.lower())]
    return jsonify({"patient_id": patient_id.lower(), "total": len(procs), "procedures": procs})


@bp.get("/patients/<patient_id>/alerts")
def get_alerts_route(patient_id):
    p = _get_patient_or_404(patient_id)
    alerts = get_alerts(patient_id.lower())
    return jsonify({
        "patient_id":   patient_id.lower(),
        "patient_name": store.patient_name(p),
        "total":        len(alerts),
        "has_critical": any(a["severity"] == "critical" for a in alerts),
        "alerts":       alerts,
    })
