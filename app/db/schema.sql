-- 5 tables. Every row keeps the original FHIR JSON in `raw` so ingestion
-- never loses information, alongside typed columns for fields we query a lot.

CREATE TABLE IF NOT EXISTS patients (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    gender      TEXT,
    birth_date  DATE,
    active      BOOLEAN DEFAULT TRUE,
    raw         JSONB
);

CREATE TABLE IF NOT EXISTS conditions (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT REFERENCES patients(id),
    display         TEXT,
    snomed_code     TEXT,
    clinical_status TEXT,
    onset_date      TEXT,
    abatement_date  TEXT,
    missing_code    BOOLEAN DEFAULT FALSE,
    raw             JSONB
);
CREATE INDEX IF NOT EXISTS idx_conditions_patient ON conditions(patient_id);

CREATE TABLE IF NOT EXISTS medications (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT REFERENCES patients(id),
    name            TEXT,
    rxnorm_code     TEXT,
    status          TEXT,
    authored_on     TEXT,
    dosage          TEXT,
    missing_dosage  BOOLEAN DEFAULT FALSE,
    raw             JSONB
);
CREATE INDEX IF NOT EXISTS idx_medications_patient ON medications(patient_id);

CREATE TABLE IF NOT EXISTS observations (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT,
    status          TEXT,
    loinc_code      TEXT,
    display         TEXT,
    effective_date  TEXT,
    value           DOUBLE PRECISION,
    unit            TEXT,
    raw             JSONB
);
CREATE INDEX IF NOT EXISTS idx_observations_patient ON observations(patient_id);
CREATE INDEX IF NOT EXISTS idx_observations_loinc ON observations(patient_id, loinc_code);

CREATE TABLE IF NOT EXISTS procedures (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT REFERENCES patients(id),
    display         TEXT,
    status          TEXT,
    performed_date  TEXT,
    raw             JSONB
);
CREATE INDEX IF NOT EXISTS idx_procedures_patient ON procedures(patient_id);

CREATE TABLE IF NOT EXISTS quality_issues (
    id            SERIAL PRIMARY KEY,
    resource_id   TEXT,
    code          TEXT,
    message       TEXT,
    detected_at   TIMESTAMP DEFAULT now()
);
