"""
Postgres query layer

Every function returns plain dicts shaped for the route handlers in
app/routes/ — no FHIR nesting beyond this point. app/store.py re-exports
these so routes never import psycopg2 directly.
"""

from app.db.connection import get_cursor


def get_patient(patient_id: str) -> dict | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM patients WHERE id = %s", (patient_id.lower(),))
        return cur.fetchone()


def get_all_patients() -> list[dict]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM patients ORDER BY name")
        return cur.fetchall()


def active_conditions(patient_id: str) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM conditions WHERE patient_id = %s AND clinical_status = 'active'",
            (patient_id.lower(),),
        )
        return cur.fetchall()


def all_conditions(patient_id: str) -> list[dict]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM conditions WHERE patient_id = %s", (patient_id.lower(),))
        return cur.fetchall()


def active_medications(patient_id: str) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM medications WHERE patient_id = %s AND status = 'active'",
            (patient_id.lower(),),
        )
        return cur.fetchall()


def observations(patient_id: str) -> list[dict]:
    """All observations for a patient, newest first."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM observations WHERE patient_id = %s ORDER BY effective_date DESC",
            (patient_id.lower(),),
        )
        return cur.fetchall()


def latest_observations(patient_id: str) -> list[dict]:
    """
    One row per LOINC code — the most recent by effective_date, with
    'amended' beating 'final' at the same timestamp (DISTINCT ON is the
    idiomatic Postgres way to do "latest row per group").
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (loinc_code) *
            FROM observations
            WHERE patient_id = %s AND status != 'entered-in-error' AND value IS NOT NULL
            ORDER BY loinc_code, effective_date DESC, (status = 'amended') DESC
            """,
            (patient_id.lower(),),
        )
        return cur.fetchall()


def observation_trend(patient_id: str, loinc_code: str) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT * FROM observations
            WHERE patient_id = %s AND loinc_code = %s AND value IS NOT NULL
            ORDER BY effective_date DESC
            """,
            (patient_id.lower(), loinc_code),
        )
        return cur.fetchall()


def bp_trend(patient_id: str) -> list[dict]:
    """Systolic + diastolic paired by timestamp, newest first."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT s.effective_date AS date, s.value AS systolic, d.value AS diastolic
            FROM observations s
            JOIN observations d
              ON d.patient_id = s.patient_id AND d.effective_date = s.effective_date
             AND d.loinc_code = '8462-4'
            WHERE s.patient_id = %s AND s.loinc_code = '8480-6'
            ORDER BY s.effective_date DESC
            """,
            (patient_id.lower(),),
        )
        return cur.fetchall()


def procedures(patient_id: str) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM procedures WHERE patient_id = %s ORDER BY performed_date DESC",
            (patient_id.lower(),),
        )
        return cur.fetchall()


def quality_log(code_filter: str | None = None) -> list[dict]:
    with get_cursor() as cur:
        if code_filter:
            cur.execute(
                "SELECT resource_id, code, message FROM quality_issues WHERE code = %s ORDER BY id",
                (code_filter.upper(),),
            )
        else:
            cur.execute("SELECT resource_id, code, message FROM quality_issues ORDER BY id")
        return cur.fetchall()


def ingestion_stats() -> dict:
    with get_cursor() as cur:
        counts = {}
        for table in ("patients", "conditions", "medications", "observations",
                       "procedures", "quality_issues"):
            cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
            counts[table] = cur.fetchone()["n"]

    return {
        "patients":            counts["patients"],
        "conditions":          counts["conditions"],
        "medications":         counts["medications"],
        "observations":        counts["observations"],
        "procedures":          counts["procedures"],
        "data_quality_issues": counts["quality_issues"],
    }
