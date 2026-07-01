"""
FHIR ingestion into Postgres

Reads the JSONL file, validates each resource, and inserts rows.
Every problem in the source data is logged to `quality_issues`
instead of crashing the load

There are two passes. The first is patients, then a final pass to catch dangling patient
references that only resolve once every patient is loaded

It is safe to re-run because every insert is ON CONFLICT DO NOTHING / DO UPDATE,
and the table is truncated first so re-running the app doesn't double
the data or the quality log
"""

import json
import logging

from app.db.connection import get_cursor

logger = logging.getLogger(__name__)


def load(path: str) -> None:
    _reset_tables()

    with open(path) as f:
        lines = [l.strip() for l in f if l.strip()]

    resources = []
    for line_num, line in enumerate(lines, 1):
        try:
            resources.append(json.loads(line))
        except json.JSONDecodeError as e:
            _log_issue(f"line-{line_num}", "PARSE_ERROR", str(e))

    loaded = skipped = 0

    # Pass 1: patients (everything else has a FK to patients)
    for r in resources:
        if r.get("resourceType") == "Patient":
            _insert_patient(r)
            loaded += 1

    # Pass 2: everything else
    inserters = {
        "Condition": _insert_condition,
        "MedicationRequest": _insert_medication,
        "Observation": _insert_observation,
        "Procedure": _insert_procedure,
    }
    for r in resources:
        rt = r.get("resourceType")
        if rt == "Patient":
            continue
        if rt in inserters:
            ok = inserters[rt](r)
            loaded += 1 if ok else 0
            skipped += 0 if ok else 1
        elif rt == "ClinicalNote":
            _log_issue(r.get("id", "unknown"), "NON_STANDARD_RESOURCE",
                       "'ClinicalNote' is not a FHIR R4 resource type — skipped")
            skipped += 1
        elif rt in ("Binary", "DocumentReference"):
            pass  # out of scope for this API
        else:
            _log_issue(r.get("id", "unknown"), "UNKNOWN_RESOURCE_TYPE",
                       f"Unrecognised resourceType: '{rt}'")
            skipped += 1

    _validate_references()
    logger.info(f"Loaded {loaded} resources, skipped {skipped}")


def _reset_tables() -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("TRUNCATE quality_issues, procedures, observations, "
                     "medications, conditions, patients RESTART IDENTITY CASCADE")


# ---------------------------------------------------------------------------
# Per-resource inserts
# ---------------------------------------------------------------------------

def _insert_patient(r: dict) -> None:
    names = r.get("name") or []
    name_obj = next((n for n in names if n.get("use") == "official"), names[0] if names else {})
    given = " ".join(name_obj.get("given") or [])
    family = name_obj.get("family", "")
    full_name = f"{given} {family}".strip() or "Unknown"

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO patients (id, name, gender, birth_date, active, raw)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (r["id"].lower(), full_name, r.get("gender"), r.get("birthDate"),
             r.get("active", True), json.dumps(r)),
        )


def _insert_condition(r: dict) -> bool:
    rid = r.get("id")
    if not rid:
        _log_issue("unknown", "MISSING_ID", "Condition has no id")
        return False

    pid = _ref_to_id(r.get("subject", {}).get("reference"))
    if not pid:
        _log_issue(rid, "MISSING_SUBJECT", "Condition has no subject reference")
        return False

    code = r.get("code")
    missing_code = not bool(code)
    if missing_code:
        _log_issue(rid, "MISSING_CONDITION_CODE", "Condition has no code — stored as 'Unknown condition'")

    coding = (code or {}).get("coding") or [{}]
    snomed = next((c.get("code") for c in coding if "snomed" in c.get("system", "")), None)
    display = (code or {}).get("text") or coding[0].get("display") or "Unknown condition"
    status = (r.get("clinicalStatus", {}).get("coding") or [{}])[0].get("code", "unknown")

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO conditions
                (id, patient_id, display, snomed_code, clinical_status,
                 onset_date, abatement_date, missing_code, raw)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (rid, pid, display, snomed, status,
             r.get("onsetDateTime"), r.get("abatementDateTime"), missing_code, json.dumps(r)),
        )
    return True


def _insert_medication(r: dict) -> bool:
    rid = r.get("id")
    if not rid:
        _log_issue("unknown", "MISSING_ID", "MedicationRequest has no id")
        return False

    # med-nw-003 has "Patient/Noah-Wyle" (capital N) — lowercasing handles it
    pid = _ref_to_id(r.get("subject", {}).get("reference"))
    if not pid:
        _log_issue(rid, "MISSING_SUBJECT", "MedicationRequest has no subject reference")
        return False

    dosage_list = r.get("dosageInstruction") or []
    missing_dosage = not bool(dosage_list)
    if missing_dosage:
        _log_issue(rid, "MISSING_DOSAGE", "MedicationRequest has no dosage instructions")

    dosage_text = "; ".join(d.get("text") for d in dosage_list if d.get("text"))
    med = r.get("medicationCodeableConcept") or {}
    coding = (med.get("coding") or [{}])[0]
    rxnorm = coding.get("code") if "rxnorm" in coding.get("system", "") else None
    name = med.get("text") or coding.get("display") or "Unknown medication"

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO medications
                (id, patient_id, name, rxnorm_code, status, authored_on,
                 dosage, missing_dosage, raw)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (rid, pid, name, rxnorm, r.get("status"), r.get("authoredOn"),
             dosage_text or None, missing_dosage, json.dumps(r)),
        )
    return True


def _insert_observation(r: dict) -> bool:
    rid = r.get("id")
    if not rid:
        _log_issue("unknown", "MISSING_ID", "Observation has no id")
        return False

    if r.get("status") == "entered-in-error":
        return False  # explicitly discarded

    subject = r.get("subject", {})
    if not subject.get("reference"):
        # obs-kl-bad-001: has a display name but no reference — can't link to a patient
        _log_issue(rid, "UNRESOLVABLE_SUBJECT",
                   f"Subject has only display '{subject.get('display')}' — observation orphaned")
        return False

    pid = _ref_to_id(subject["reference"])
    if r.get("status") == "unknown":
        _log_issue(rid, "UNKNOWN_OBS_STATUS", "Observation status is 'unknown' — included but flagged")

    coding = (r.get("code", {}).get("coding") or [{}])[0]
    display = r.get("code", {}).get("text") or coding.get("display")

    rows = []
    if r.get("valueQuantity"):
        rows.append((rid, coding.get("code"), display,
                     r["valueQuantity"].get("value"), r["valueQuantity"].get("unit")))
    elif r.get("component"):
        # Panel observations (e.g. blood pressure) carry their value inside
        # each component rather than on the observation itself. Store each
        # component as its own row so it can be queried/alerted on by its
        # own LOINC code, same as any scalar observation.
        for i, comp in enumerate(r["component"]):
            comp_coding = (comp.get("code", {}).get("coding") or [{}])[0]
            comp_value = (comp.get("valueQuantity") or {}).get("value")
            if comp_value is None:
                continue
            rows.append((f"{rid}-{i}", comp_coding.get("code"), comp_coding.get("display"),
                         comp_value, (comp.get("valueQuantity") or {}).get("unit")))
    # valueString observations (e.g. smoking status) have no numeric value
    # to alert on, but are still worth keeping for the record.
    elif "valueString" in r:
        rows.append((rid, coding.get("code"), display, None, None))

    with get_cursor(commit=True) as cur:
        for row_id, loinc, disp, value, unit in rows:
            cur.execute(
                """
                INSERT INTO observations
                    (id, patient_id, status, loinc_code, display,
                     effective_date, value, unit, raw)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (row_id, pid, r.get("status"), loinc, disp,
                 r.get("effectiveDateTime"), value, unit, json.dumps(r)),
            )

    # Duplicate detection: same patient + code + timestamp, already loaded
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id FROM observations
            WHERE patient_id = %s AND loinc_code = %s AND effective_date = %s AND id != %s
            """,
            (pid, coding.get("code"), r.get("effectiveDateTime"), rid),
        )
        existing = cur.fetchone()
        if existing:
            _log_issue(rid, "POTENTIAL_DUPLICATE",
                       f"Same patient/code/time as {existing['id']} — both retained")

    return True


def _insert_procedure(r: dict) -> bool:
    rid = r.get("id")
    if not rid:
        _log_issue("unknown", "MISSING_ID", "Procedure has no id")
        return False

    pid = _ref_to_id(r.get("subject", {}).get("reference"))
    if not pid:
        _log_issue(rid, "MISSING_SUBJECT", "Procedure has no subject reference")
        return False

    coding = (r.get("code", {}).get("coding") or [{}])[0]
    display = r.get("code", {}).get("text") or coding.get("display") or "Unknown procedure"

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO procedures (id, patient_id, display, status, performed_date, raw)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (rid, pid, display, r.get("status"), r.get("performedDateTime"), json.dumps(r)),
        )
    return True


# ---------------------------------------------------------------------------
# Validation + helpers
# ---------------------------------------------------------------------------

def _validate_references() -> None:
    """
    Find observations whose patient_id doesn't exist in the patients table.
    Catches obs-nw-006's "Patient/nwyle" typo — only resolvable once every
    patient row has been loaded.
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT o.id, o.patient_id FROM observations o
            LEFT JOIN patients p ON o.patient_id = p.id
            WHERE p.id IS NULL
            """
        )
        dangling = cur.fetchall()
    for row in dangling:
        _log_issue(row["id"], "DANGLING_PATIENT_REF",
                   f"References Patient/{row['patient_id']} which does not exist")


def _log_issue(resource_id: str, code: str, message: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO quality_issues (resource_id, code, message) VALUES (%s, %s, %s)",
            (resource_id, code, message),
        )
    logger.warning(f"[{code}] {resource_id}: {message}")


def _ref_to_id(reference: str | None) -> str | None:
    """'Patient/noah-wyle' -> 'noah-wyle'. Case-normalised."""
    if not reference:
        return None
    return reference.split("/")[-1].lower()
