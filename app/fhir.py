"""
Response formatting to pick the fields callers want and rename a couple
for clarity
"""

from app.store import patient_name, patient_age


def fmt_patient(p: dict) -> dict:
    birth_date = p.get("birth_date")
    return {
        "id":         p["id"],
        "name":       patient_name(p),
        "gender":     p.get("gender"),
        "birth_date": str(birth_date) if birth_date else None,
        "age":        patient_age(birth_date),
        "active":     p.get("active", True),
    }


def fmt_condition(c: dict) -> dict:
    return {
        "id":              c["id"],
        "display":         c.get("display") or "Unknown condition",
        "snomed_code":     c.get("snomed_code"),
        "clinical_status": c.get("clinical_status", "unknown"),
        "onset":           c.get("onset_date"),
        "abatement":       c.get("abatement_date"),
        "_missing_code":   c.get("missing_code", False),
    }


def fmt_medication(m: dict) -> dict:
    return {
        "id":              m["id"],
        "name":            m.get("name") or "Unknown medication",
        "rxnorm_code":     m.get("rxnorm_code"),
        "status":          m.get("status"),
        "authored_on":     m.get("authored_on"),
        "dosage":          m.get("dosage"),
        "_missing_dosage": m.get("missing_dosage", False),
    }


def fmt_observation(o: dict) -> dict:
    return {
        "id":             o["id"],
        "status":         o.get("status"),
        "loinc_code":     o.get("loinc_code"),
        "display":        o.get("display"),
        "effective_date": o.get("effective_date"),
        "value":          o.get("value"),
        "unit":           o.get("unit"),
    }


def fmt_procedure(p: dict) -> dict:
    return {
        "id":        p["id"],
        "display":   p.get("display") or "Unknown procedure",
        "status":    p.get("status"),
        "performed": p.get("performed_date"),
    }
