# Novellia Health API

A clinical data API that takes FHIR-formatted healthcare records and makes them actually useful.
The data is queryable by patient, filterable by population, and readable by a human.

Built with Python, Flask, and Postgres.


## Running it

Docker is required

```bash
docker compose up --build
```

This starts Postgres and the API together. 
On startup the API creates the schema, loads the FHIR data, and is ready to take requests.

```bash
curl localhost:3000/health
```

To stop it and clear the database:

```bash
docker compose down -v
```

### Pointing it at a different data file

The app reads whatever file path is in the `FHIR_DATA_FILE` environment variable. It defaults to `data/fhir_data.jsonl` but you can change it in `docker-compose.yml`:

```yaml
environment:
  FHIR_DATA_FILE: data/your_file.jsonl
```

The file just needs to be a JSONL file where each line is a FHIR resource. The loader handles anything it doesn't recognize by logging and then skipping, so the app does not crash. 


## What it does

Raw FHIR is deeply nested JSON built for data interchange, not for people. This API answers the actual questions that clinicians and care coordinators have:

Physician - What do I need to know before I walk in? --> `GET /patients/:id/summary`
Care coordinator - Which patients need attention today? --> `GET /analytics/worklist`
Data team - Is the data from this clinic clean? --> `GET /admin/quality/report`

## Endpoints

### Health check
```bash
curl localhost:3000/health
```

### Patients

```bash
# List everyone
curl localhost:3000/patients

# One patient's demographics
curl localhost:3000/patients/noah-wyle

# Pre-visit summary — conditions, meds, alerts, vitals, trends in one call
curl localhost:3000/patients/noah-wyle/summary
curl localhost:3000/patients/shabana-azeez/summary
curl localhost:3000/patients/tracy-ifeachor/summary

# Pretty-print any response
curl -s localhost:3000/patients/noah-wyle/summary | python3 -m json.tool

# Conditions (filter by status)
curl localhost:3000/patients/patrick-ball/conditions
curl "localhost:3000/patients/patrick-ball/conditions?status=resolved"

# Medications
curl localhost:3000/patients/fiona-dourif/medications

# Observations
curl localhost:3000/patients/noah-wyle/observations
curl localhost:3000/patients/noah-wyle/observations/latest
curl localhost:3000/patients/noah-wyle/observations/trend/4548-4

# Alerts
curl localhost:3000/patients/shabana-azeez/alerts
curl localhost:3000/patients/tracy-ifeachor/alerts

# Plain-English summary paragraph
curl localhost:3000/patients/noah-wyle/narrative
curl -s localhost:3000/patients/noah-wyle/narrative | python3 -c "import json,sys; print(json.load(sys.stdin)['narrative'])"
```

### Analytics

```bash
# All patients ranked by urgency
curl localhost:3000/analytics/worklist
curl "localhost:3000/analytics/worklist?severity=critical"

# Plain-text table version, good for terminal reading
curl -s localhost:3000/analytics/worklist/summary | python3 -c "import json,sys; print(json.load(sys.stdin)['table'])"

# Filter by condition, medication, age, gender — combinable
curl "localhost:3000/analytics/cohort?condition=diabetes"
curl "localhost:3000/analytics/cohort?medication=metformin"
curl "localhost:3000/analytics/cohort?gender=female&max_age=40"
curl "localhost:3000/analytics/cohort?condition=hypertension&gender=female"

# Population-level stats
curl localhost:3000/analytics/conditions
curl localhost:3000/analytics/medications
```

### Data quality

```bash
# Plain-text report — readable directly in the terminal
curl localhost:3000/admin/quality/report

# Raw counts by resource type
curl localhost:3000/admin/stats

# Full issue log, filterable
curl localhost:3000/admin/quality
curl "localhost:3000/admin/quality?code=DANGLING_PATIENT_REF"
```

## How bad data is handled

The loader never crashes on unexpected input. Every problem gets logged to a quality_issues table with a code explaining what went wrong and which record caused it. The data is still loaded wherever possible and a record with a missing field is flagged, not dropped.

| What went wrong | Which record | Code |
|---|---|---|
| Patient ID typo in a reference | `obs-nw-006` references `Patient/nwyle` | `DANGLING_PATIENT_REF` |
| Observation with no patient reference | `obs-kl-bad-001` | `UNRESOLVABLE_SUBJECT` |
| Condition with no code | `cond-nw-bad-001` | `MISSING_CONDITION_CODE` |
| Medication with no dosage | `med-fd-002` | `MISSING_DOSAGE` |
| Duplicate observation, same time and code | `obs-nw-dup-001` | `POTENTIAL_DUPLICATE` |
| Non-standard resource type | `note-robby-001` (ClinicalNote) | `NON_STANDARD_RESOURCE` |

The typo case (Patient/nwyle) is worth calling out. It's only detectable in a second pass after every patient has loaded because you can't know a reference is dangling until you've seen every patient that exists. As a result, Noah's blood pressure trend shows only one data point instead of two, which is visible and explainable from the quality log.

The amended-observation case is handled correctly without flagging: Tracy has two O2 readings at the same timestamp. A final one at 94% and one amended at 96%. The system picks the amended value, so her alerts show no critical issues. The 94% reading would have triggered one.


## Schema

There are 5 tables.
Every row keeps the original FHIR JSON in a raw column alongside typed columns for fields that get queried such as dates, status codes, and LOINC codes. 
This is necessary so ingestion never loses information even if the typed schema doesn't cover a field.

Blood pressure is worth calling out specifically. In FHIR it arrives as a panel with systolic and diastolic nested inside a component array. 
This API flattens those into their own rows in the observations table at load time, each with its own LOINC code. 
That means the alert engine and the trend endpoint treat blood pressure components exactly like any other observation.

patient_id is plain text rather than a UUID because the source data uses IDs like noah-wyle. Observations intentionally have no foreign key constraint back to patients.

## Alert thresholds

| Metric | Threshold | Severity |
|---|---|---|
| Systolic BP | > 140 mmHg | warning |
| Diastolic BP | > 90 mmHg | warning |
| HbA1c | > 8.0% | critical |
| HbA1c | 7.0–8.0% | warning |
| O2 saturation | < 95% | critical |
| Total cholesterol | > 200 mg/dL | warning |
| Fasting glucose | > 126 mg/dL | warning |
| Heart rate | > 100 bpm | warning |
| TSH | > 4.5 mIU/L | warning |


## Authentication

Not implemented.
For production this would be token validation in Flask middleware, role-based access between clinical and admin endpoints, and audit logging on every patient data access complying with HIPAA requirement.

## Tools and AI used

Python/Flask: this is what I know. Flask is lightweight and gets out of the way, which suits a project where the interesting decisions are in the data layer rather than the framework.

Postgres: straightforward choice for structured clinical data that needs to be queried by patient, by LOINC code, and by date. Raw SQL over an ORM because for five tables with simple queries it's more readable and easier to debug.

Docker: standard way to ship a Postgres-backed app with a one-command setup. The goal was that a reviewer should be able to run this without installing anything beyond Docker.

Claude: I used Claude as a development assistant throughout the project, similar to how I would use documentation or other online/in-person resources. 
I designed the schema and overall architecture, including the two-pass loading strategy and alert engine approach. 
I used AI to help iterate on implementation details, catch bugs, and move faster, but I reviewed and validated the code end-to-end and made the final decisions on tradeoffs and design.