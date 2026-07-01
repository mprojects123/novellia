"""
app.store is the only module routes import for data access. It re-exports
the Postgres query functions and adds small helpers (age calculation,
display name) that don't belong in SQL
"""

from datetime import date

from app.db.queries import (  # noqa: F401 — re-exported for routes
    get_patient,
    get_all_patients,
    active_conditions,
    all_conditions,
    active_medications,
    observations,
    latest_observations,
    observation_trend,
    bp_trend,
    procedures,
    quality_log,
    ingestion_stats,
)


def patient_name(patient: dict) -> str:
    return patient.get("name") or "Unknown"


def patient_age(birth_date) -> int | None:
    if not birth_date:
        return None
    if isinstance(birth_date, str):
        try:
            birth_date = date.fromisoformat(birth_date)
        except ValueError:
            return None
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
