"""
Admin / data quality endpoints

GET /admin/stats                Ingestion counts by resource type
GET /admin/quality              Full issue log (filterable by ?code=)
GET /admin/quality/summary      Grouped summary with counts (JSON)
GET /admin/quality/report       Same summary as plain readable text —
                                curl this directly, no pipe needed
"""

from flask import Blueprint, jsonify, request, Response
from collections import defaultdict
import app.store as store

bp = Blueprint("admin", __name__)

# Plain-English explanation for each issue code.
# Anything not listed here gets a generic fallback.
EXPLANATIONS = {
    "POTENTIAL_DUPLICATE": (
        "Two observations share the same patient, LOINC code, and timestamp. "
        "Both are retained. One may be an amended correction — check the status field."
    ),
    "DANGLING_PATIENT_REF": (
        "This observation references a patient ID that does not exist in the dataset. "
        "It cannot be linked to any patient record. Likely a typo in the source data."
    ),
    "MISSING_DOSAGE": (
        "This medication arrived with an empty dosage instruction. "
        "It is still stored and shown on the patient's medication list, but the dosage needs to be confirmed."
    ),
    "MISSING_CONDITION_CODE": (
        "This condition record has no code — no SNOMED, no display text. "
        "It is stored and flagged on the patient's summary so it is not lost, but it is degraded data."
    ),
    "UNRESOLVABLE_SUBJECT": (
        "This observation has a patient display name but no reference ID. "
        "There is no way to programmatically link it to a patient record, so it was orphaned."
    ),
    "NON_STANDARD_RESOURCE": (
        "This resource type is not part of the FHIR R4 standard. "
        "The system did not know how to handle it and logged it rather than crashing."
    ),
    "UNKNOWN_OBS_STATUS": (
        "This observation has a status of 'unknown'. "
        "It is included in the dataset but flagged for clinical review."
    ),
    "PARSE_ERROR": (
        "This line in the source file could not be parsed as valid JSON and was skipped."
    ),
    "UNKNOWN_RESOURCE_TYPE": (
        "This resource type was not recognised and was skipped."
    ),
}


@bp.get("/admin/stats")
def stats():
    return jsonify(store.ingestion_stats())


@bp.get("/admin/quality")
def quality_log():
    issues = store.quality_log(request.args.get("code"))
    return jsonify({"total": len(issues), "issues": issues})


@bp.get("/admin/quality/summary")
def quality_summary():
    issues = store.quality_log()
    by_code: dict[str, dict] = defaultdict(lambda: {"count": 0, "examples": []})
    for issue in issues:
        entry = by_code[issue["code"]]
        entry["count"] += 1
        if len(entry["examples"]) < 3:
            entry["examples"].append(issue["resource_id"])

    summary = sorted(
        [{"code": code, **data} for code, data in by_code.items()],
        key=lambda r: -r["count"],
    )
    return jsonify({"total_issues": len(issues), "unique_types": len(summary), "summary": summary})


@bp.get("/admin/quality/report")
def quality_report():
    """
    Plain-text data quality report that is readable directly in the terminal.
    No JSON pipe needed, just: curl localhost:3000/admin/quality/report
    """
    issues = store.quality_log()
    by_code: dict[str, dict] = defaultdict(lambda: {"count": 0, "examples": []})
    for issue in issues:
        entry = by_code[issue["code"]]
        entry["count"] += 1
        if len(entry["examples"]) < 3:
            entry["examples"].append(issue["resource_id"])

    summary = sorted(by_code.items(), key=lambda x: -x[1]["count"])

    lines = []
    lines.append("=" * 60)
    lines.append("DATA QUALITY REPORT")
    lines.append(f"Total issues: {len(issues)}  |  Unique types: {len(summary)}")
    lines.append("=" * 60)

    for code, data in summary:
        lines.append("")
        lines.append(f"{code}  (x{data['count']})")
        lines.append(f"Examples: {', '.join(data['examples'])}")
        explanation = EXPLANATIONS.get(code, "No further explanation available.")
        lines.append(f"  {explanation}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("All issues were logged at load time. No records were")
    lines.append("silently dropped. Use GET /admin/quality?code=<CODE>")
    lines.append("to see every affected resource ID for a specific issue.")
    lines.append("=" * 60)

    return Response("\n".join(lines) + "\n", mimetype="text/plain")
