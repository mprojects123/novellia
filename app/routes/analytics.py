"""
Population analytics endpoints

GET /analytics/worklist          All patients sorted by clinical urgency
GET /analytics/cohort             Filter patients by condition/medication/demographics
GET /analytics/conditions        Condition prevalence
GET /analytics/medications       Medication frequency
GET /analytics/worklist/summary  Plain-text table for terminal reading
"""

from flask import Blueprint, jsonify, request
import app.store as store
from app.fhir import fmt_patient
from app.alerts import get_alerts

bp = Blueprint("analytics", __name__)


@bp.get("/analytics/worklist")
def worklist():
    """The care coordinator's view — every patient ranked by urgency."""
    severity_filter = request.args.get("severity")

    rows = []
    for p in store.get_all_patients():
        pid = p["id"]
        alerts = get_alerts(pid)
        critical = [a for a in alerts if a["severity"] == "critical"]
        warnings = [a for a in alerts if a["severity"] == "warning"]

        if severity_filter == "critical" and not critical:
            continue
        if severity_filter == "warning" and not (critical or warnings):
            continue

        rows.append({
            "patient_id":     pid,
            "name":           store.patient_name(p),
            "age":            store.patient_age(p.get("birth_date")),
            "gender":         p.get("gender"),
            "critical_count": len(critical),
            "warning_count":  len(warnings),
            "top_alerts":     alerts[:3],
        })

    rows.sort(key=lambda r: (-r["critical_count"], -r["warning_count"]))
    return jsonify({"total": len(rows), "filter": severity_filter or "all", "worklist": rows})


@bp.get("/analytics/cohort")
def cohort():
    """
    Combinable filters:
      ?condition=diabetes     partial text match on condition display
      ?medication=metformin   partial text match on medication name
      ?gender=female
      ?min_age=40
      ?max_age=65
    """
    condition_q  = (request.args.get("condition") or "").lower()
    medication_q = (request.args.get("medication") or "").lower()
    gender_q     = (request.args.get("gender") or "").lower()
    min_age      = request.args.get("min_age", type=int)
    max_age      = request.args.get("max_age", type=int)

    results = []
    for p in store.get_all_patients():
        age = store.patient_age(p.get("birth_date"))

        if gender_q and (p.get("gender") or "").lower() != gender_q:
            continue
        if min_age is not None and (age is None or age < min_age):
            continue
        if max_age is not None and (age is None or age > max_age):
            continue

        if condition_q:
            texts = [(c.get("display") or "").lower() for c in store.active_conditions(p["id"])]
            if not any(condition_q in t for t in texts):
                continue

        if medication_q:
            names = [(m.get("name") or "").lower() for m in store.active_medications(p["id"])]
            if not any(medication_q in n for n in names):
                continue

        results.append(fmt_patient(p))

    return jsonify({"total": len(results), "patients": results})


@bp.get("/analytics/conditions")
def condition_prevalence():
    counts: dict[str, list] = {}
    for p in store.get_all_patients():
        for c in store.active_conditions(p["id"]):
            label = c.get("display") or "Unknown"
            counts.setdefault(label, []).append(p["id"])

    total = len(store.get_all_patients())
    rows = sorted(
        [
            {"condition": label, "patient_count": len(ids),
             "prevalence_pct": round(len(ids) / total * 100, 1), "patient_ids": ids}
            for label, ids in counts.items()
        ],
        key=lambda r: -r["patient_count"],
    )
    return jsonify({"total_patients": total, "conditions": rows})


@bp.get("/analytics/medications")
def medication_frequency():
    counts: dict[str, list] = {}
    for p in store.get_all_patients():
        for m in store.active_medications(p["id"]):
            name = m.get("name") or "Unknown"
            counts.setdefault(name, []).append(p["id"])

    rows = sorted(
        [{"medication": name, "patient_count": len(ids), "patient_ids": ids}
         for name, ids in counts.items()],
        key=lambda r: -r["patient_count"],
    )
    return jsonify({"total_patients": len(store.get_all_patients()), "medications": rows})


@bp.get("/analytics/worklist/summary")
def worklist_summary():
    """A compact, human-readable 'who needs attention today' table."""
    rows = []
    for p in store.get_all_patients():
        pid = p["id"]
        alerts = get_alerts(pid)
        critical = [a for a in alerts if a["severity"] == "critical"]
        warnings = [a for a in alerts if a["severity"] == "warning"]

        status = "CRITICAL" if critical else ("WARNING" if warnings else "OK")
        top = alerts[0]["label"] if alerts else "—"

        rows.append({
            "status":         status,
            "name":           store.patient_name(p),
            "age":            store.patient_age(p.get("birth_date")),
            "gender":         p.get("gender", ""),
            "critical_count": len(critical),
            "warning_count":  len(warnings),
            "top_alert":      top,
            "patient_id":     pid,
        })

    rows.sort(key=lambda r: (
        0 if r["status"] == "CRITICAL" else 1 if r["status"] == "WARNING" else 2,
        -r["critical_count"], -r["warning_count"],
    ))

    header  = f"{'STATUS':<10} {'NAME':<25} {'AGE':<5} {'CRIT':<6} {'WARN':<6} TOP ALERT"
    divider = "-" * 90
    table_rows = [
        f"{r['status']:<10} {r['name']:<25} {str(r['age']):<5} {r['critical_count']:<6} {r['warning_count']:<6} {r['top_alert']}"
        for r in rows
    ]
    table = "\n".join([header, divider] + table_rows)

    return jsonify({
        "total":          len(rows),
        "critical_count": sum(1 for r in rows if r["status"] == "CRITICAL"),
        "warning_count":  sum(1 for r in rows if r["status"] == "WARNING"),
        "ok_count":       sum(1 for r in rows if r["status"] == "OK"),
        "table":          table,
        "rows":           rows,
    })
