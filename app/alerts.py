"""
Clinical alert engine

Runs against the latest observation per LOINC code for a patient and returns structured alerts sorted by severity
(critical first).
"""

from app.store import latest_observations

RULES = [
    {
        "loinc":    "8480-6",   # systolic BP
        "label":    "Elevated systolic blood pressure",
        "test":     lambda v: v > 140,
        "severity": "warning",
        "context":  "Target <130/80 mmHg. >140 indicates Stage 2 hypertension.",
    },
    {
        "loinc":    "8462-4",   # diastolic BP
        "label":    "Elevated diastolic blood pressure",
        "test":     lambda v: v > 90,
        "severity": "warning",
        "context":  "Diastolic >90 mmHg with systolic >140 = Stage 2 hypertension.",
    },
    {
        "loinc":    "4548-4",   # HbA1c
        "label":    "HbA1c critically elevated (>8%)",
        "test":     lambda v: v > 8.0,
        "severity": "critical",
        "context":  "ADA target <7% for most patients. >8% = poorly controlled diabetes.",
    },
    {
        "loinc":    "4548-4",
        "label":    "HbA1c above target (7–8%)",
        "test":     lambda v: 7.0 < v <= 8.0,
        "severity": "warning",
        "context":  "Above ADA target of <7%. Review medication and lifestyle.",
    },
    {
        "loinc":    "59408-5",  # O2 saturation
        "label":    "Low oxygen saturation",
        "test":     lambda v: v < 95,
        "severity": "critical",
        "context":  "SpO2 <95% warrants evaluation. <90% is a respiratory emergency.",
    },
    {
        "loinc":    "2093-3",   # total cholesterol
        "label":    "Total cholesterol elevated",
        "test":     lambda v: v > 200,
        "severity": "warning",
        "context":  "Desirable <200 mg/dL. Assess cardiovascular risk.",
    },
    {
        "loinc":    "2339-0",   # fasting glucose
        "label":    "Fasting glucose elevated",
        "test":     lambda v: v > 126,
        "severity": "warning",
        "context":  "Fasting glucose >126 mg/dL meets ADA criteria for diabetes.",
    },
    {
        "loinc":    "8867-4",   # heart rate
        "label":    "Tachycardia",
        "test":     lambda v: v > 100,
        "severity": "warning",
        "context":  "Resting HR >100 bpm. Rule out pain, anxiety, fever, arrhythmia.",
    },
    {
        "loinc":    "11579-0",  # TSH
        "label":    "TSH elevated",
        "test":     lambda v: v > 4.5,
        "severity": "warning",
        "context":  "TSH >4.5 mIU/L suggests hypothyroidism. Check free T4.",
    },
]


def get_alerts(patient_id: str) -> list[dict]:
    fired = []
    for obs in latest_observations(patient_id):
        for rule in RULES:
            if rule["loinc"] != obs["loinc_code"]:
                continue
            if not rule["test"](obs["value"]):
                continue
            fired.append({
                "severity":           rule["severity"],
                "label":              rule["label"],
                "context":            rule["context"],
                "value":              obs["value"],
                "unit":               obs.get("unit"),
                "loinc_code":         obs["loinc_code"],
                "observation_id":     obs["id"],
                "effective_datetime": obs.get("effective_date"),
            })

    fired.sort(key=lambda a: 0 if a["severity"] == "critical" else 1)
    return fired
