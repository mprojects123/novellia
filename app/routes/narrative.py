"""
GET /patients/<id>/narrative

Generates a plain-English clinical briefs from structured alert/trends built entirely from what's already in Postgres.
"""

from flask import Blueprint, jsonify, abort
import app.store as store
from app.alerts import get_alerts

bp = Blueprint("narrative", __name__)


def _build_narrative(patient_id: str) -> str:
    p = store.get_patient(patient_id)
    name = store.patient_name(p)
    age = store.patient_age(p.get("birth_date"))
    gender = p.get("gender", "patient")

    cond_names = [c["display"] for c in store.active_conditions(patient_id)]
    med_names = [m["name"] for m in store.active_medications(patient_id)]

    alerts = get_alerts(patient_id)
    critical = [a for a in alerts if a["severity"] == "critical"]
    warnings = [a for a in alerts if a["severity"] == "warning"]

    hba1c = store.observation_trend(patient_id, "4548-4")

    if cond_names:
        cond_str = ", ".join(cond_names[:-1]) + (" and " + cond_names[-1] if len(cond_names) > 1 else cond_names[0])
        sentence1 = f"{name} is a {age}-year-old {gender} with {cond_str}."
    else:
        sentence1 = f"{name} is a {age}-year-old {gender} with no active conditions on record."

    sentence2 = ""
    if len(hba1c) >= 2:
        latest_val, previous_val = hba1c[0]["value"], hba1c[1]["value"]
        direction = "improved" if latest_val < previous_val else "worsened"
        sentence2 = f"HbA1c has {direction} from {previous_val}% to {latest_val}% between visits."
    elif critical:
        sentence2 = f"Active critical alert: {critical[0]['label']} ({critical[0]['value']} {critical[0].get('unit', '')}).".strip()
    elif warnings:
        labels = "; ".join(f"{w['label']} ({w['value']} {w.get('unit', '')})" for w in warnings[:2])
        sentence2 = f"Flagged for review: {labels}."

    if med_names:
        sentence3 = f"Current medications: {', '.join(med_names)}."
    else:
        sentence3 = "No active medications on record."

    return " ".join(s for s in [sentence1, sentence2, sentence3] if s)


@bp.get("/patients/<patient_id>/narrative")
def get_narrative(patient_id):
    p = store.get_patient(patient_id)
    if not p:
        abort(404, description=f"Patient '{patient_id}' not found")

    pid = patient_id.lower()
    return jsonify({
        "patient_id":   pid,
        "patient_name": store.patient_name(p),
        "narrative":    _build_narrative(pid),
    })
