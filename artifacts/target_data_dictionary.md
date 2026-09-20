# Data Dictionary

## Table: `billing_transactions`

### `txn_id`
- **Source Lineage:** `billing_transactions.txn_id`
- **Transformation Logic:** IDENTITY
- **Null Handling:** N/A (primary key, non-null)
- **Edge Cases:** None
- **Human Reviewed:** No

### `encounter_id`
- **Source Lineage:** `billing_transactions.enc_id`
- **Transformation Logic:** `enc_id`
- **Null Handling:** Preserve NULLs as unassociated transactions (e.g., general fees or unlinked charges)
- **Edge Cases:** Nullable with a small null rate (~1.9%), likely transactions without an encounter association
- **Human Reviewed:** No

### `transaction_amount`
- **Source Lineage:** `billing_transactions.txn_amt`
- **Transformation Logic:** `txn_amt`
- **Null Handling:** Column is non-nullable (0.0 null rate); pass through directly.
- **Edge Cases:** None identified; non-nullable decimal amounts for financial transactions.
- **Human Reviewed:** No

### `transaction_status_code`
- **Source Lineage:** `billing_transactions.txn_st_cd`
- **Transformation Logic:** `CASE txn_st_cd WHEN 'P' THEN 'PAID' WHEN 'O' THEN 'OUTSTANDING' WHEN 'R' THEN 'REFUNDED' WHEN 'W' THEN 'WRITE_OFF' ELSE 'INVALID' END`
- **Null Handling:** Since null rate is 0.0%, no nulls expected, but map unrecognized values to 'UNKNOWN'
- **Edge Cases:** Contains dirty data or error flags like '?' and '!'; values are completely undocumented single-character codes
- **Human Reviewed:** Yes — Override Note: legacy billing codes: W=Write-off (not Waiting), O=Outstanding (not Other). Corrected per actual system documentation.

### `payment_method_code`
- **Source Lineage:** `billing_transactions.pmt_mthd_cd`
- **Transformation Logic:** `CASE pmt_mthd_cd WHEN 'CC' THEN 'CREDIT_CARD' WHEN 'IN' THEN 'INVOICE' WHEN 'CA' THEN 'CASH' WHEN 'CH' THEN 'CHECK' ELSE 'UNKNOWN' END`
- **Null Handling:** Leave NULLs as NULL or map to a default string like 'UN' (Unknown) depending on warehouse schema standards.
- **Edge Cases:** NULL values represent unrecorded or cash-on-delivery/unknown methods (15.18% null rate)
- **Human Reviewed:** No

### `transaction_timestamp`
- **Source Lineage:** `billing_transactions.txn_dt`
- **Transformation Logic:** `CAST(txn_dt AS TIMESTAMP)`
- **Null Handling:** Column is non-nullable (Nullable: False), so no null handling required.
- **Edge Cases:** None
- **Human Reviewed:** No

---

## Table: `encounters`

### `enc_id`
- **Source Lineage:** `encounters.enc_id`
- **Transformation Logic:** IDENTITY
- **Null Handling:** N/A (primary key, non-null)
- **Edge Cases:** None
- **Human Reviewed:** No

### `patient_id`
- **Source Lineage:** `encounters.pat_id`
- **Transformation Logic:** `pat_id`
- **Null Handling:** Keep NULLs as NULL since the column is nullable and refers to missing or unassigned patient records
- **Edge Cases:** Nullable in 2.99% of rows, which might represent unlinked or anonymous encounters
- **Human Reviewed:** No

### `provider_id`
- **Source Lineage:** `encounters.prov_id`
- **Transformation Logic:** `CAST(prov_id AS INTEGER)`
- **Null Handling:** Retain NULLs as NULL in the target warehouse
- **Edge Cases:** Null values represent unassigned or unrecorded providers (approx 2.9%)
- **Human Reviewed:** No

### `encounter_timestamp`
- **Source Lineage:** `encounters.enc_dt`
- **Transformation Logic:** `CAST(enc_dt AS TIMESTAMP)`
- **Null Handling:** Column is NOT NULL, so no null handling required beyond standard pass-through.
- **Edge Cases:** None identified. Timestamps are standard datetime objects.
- **Human Reviewed:** No

### `encounter_type_code`
- **Source Lineage:** `encounters.enc_typ_cd`
- **Transformation Logic:** `CASE enc_typ_cd WHEN 'TC' THEN 'TELEHEALTH' WHEN 'OV' THEN 'OFFICE_VISIT' WHEN 'IP' THEN 'INPATIENT' WHEN 'ER' THEN 'EMERGENCY' ELSE 'UNKNOWN' END`
- **Null Handling:** NOT NULL constraint in source, but invalid values ('?', '!', 'Z') should be mapped to a standard 'UNKNOWN' or 'OTHER' category, or handled appropriately in the transformation rule.
- **Edge Cases:** Unknown/invalid codes present ('Z', '?', '!') which need standardization or mapping to NULL
- **Human Reviewed:** No

### `encounter_amount`
- **Source Lineage:** `encounters.enc_amt`
- **Transformation Logic:** `CAST(enc_amt AS DECIMAL(10,2))`
- **Null Handling:** Pass through NULL values if missing, or default to 0.00 depending on the target financial schema requirements
- **Edge Cases:** Zero or negative amounts might appear in real data even if not in samples; currency precision needs to align with the target schema standard
- **Human Reviewed:** No

### `encounter_status`
- **Source Lineage:** `encounters.enc_st`
- **Transformation Logic:** `CASE enc_st WHEN 'C' THEN 'COMPLETED' WHEN 'O' THEN 'OPEN' WHEN 'X' THEN 'CANCELLED' ELSE 'UNKNOWN' END`
- **Null Handling:** Since null rate is 0.0, every row has a status code, but invalid characters should likely be mapped to UNKNOWN or NULL in the modern warehouse.
- **Edge Cases:** Encountered anomalous values like '!', '?', and 'Z' which do not fit standard healthcare encounter status codes (like 'C' for Completed, 'O' for Open, 'X' for Cancelled).
- **Human Reviewed:** Yes — Override Note: no changes

---

## Table: `insurance_plans`

### `plan_id`
- **Source Lineage:** `insurance_plans.plan_id`
- **Transformation Logic:** IDENTITY
- **Null Handling:** N/A (primary key, non-null)
- **Edge Cases:** None
- **Human Reviewed:** No

### `plan_name`
- **Source Lineage:** `insurance_plans.plan_nm`
- **Transformation Logic:** `TRIM(plan_nm)`
- **Null Handling:** Since nullable is False and null rate is 0.0, no null handling is necessary beyond standard NOT NULL enforcement in the target schema.
- **Edge Cases:** None observed
- **Human Reviewed:** No

### `plan_type_code`
- **Source Lineage:** `insurance_plans.plan_typ_cd`
- **Transformation Logic:** `CASE plan_typ_cd WHEN 'H' THEN 'HMO' WHEN 'P' THEN 'PPO' WHEN 'M' THEN 'MEDICARE' ELSE 'OTHER' END`
- **Null Handling:** NOT NULL constraint in source means nulls should not be expected; map unknown/invalid codes to 'UNKNOWN' or retain source code.
- **Edge Cases:** 'X' is ambiguous and could represent an unknown, canceled, or legacy plan type
- **Human Reviewed:** No

### `is_active`
- **Source Lineage:** `insurance_plans.plan_active`
- **Transformation Logic:** `CAST(plan_active AS BOOLEAN)`
- **Null Handling:** If NULL, default to 1 (active) or keep NULL depending on business requirements; typical flag behavior allows FALSE/0 or NULL.
- **Edge Cases:** Cardinality is 1; all sample values are 1, so we cannot observe a 0 (inactive) state in the sample data, though the name and type strongly imply a boolean/flag.
- **Human Reviewed:** No

---

## Table: `patient_records`

### `pat_id`
- **Source Lineage:** `patient_records.pat_id`
- **Transformation Logic:** IDENTITY
- **Null Handling:** N/A (primary key, non-null)
- **Edge Cases:** None
- **Human Reviewed:** No

### `first_name`
- **Source Lineage:** `patient_records.pat_fname`
- **Transformation Logic:** `TRIM(pat_fname)`
- **Null Handling:** NOT NULL constraint in source, so no nulls expected. If any nulls are encountered during migration, flag as a data quality error or map to an empty string depending on downstream schema requirements.
- **Edge Cases:** Names with spaces or hyphenations (e.g., Mary Ann, Jean-Luc) need to be preserved correctly; proper capitalization in sample data ('Anna', 'Christopher') indicates mixed case.
- **Human Reviewed:** No

### `patient_last_name`
- **Source Lineage:** `patient_records.pat_lname`
- **Transformation Logic:** `TRIM(pat_lname)`
- **Null Handling:** Column is NOT NULL; pass through values directly.
- **Edge Cases:** Hyphenated last names or names with apostrophes may exist beyond the sample set.
- **Human Reviewed:** No

### `date_of_birth`
- **Source Lineage:** `patient_records.dob`
- **Transformation Logic:** `CAST(dob AS DATE)`
- **Null Handling:** Allow NULLs as nullable is True and null rate is 0.0 (though missing values could occur in future loads).
- **Edge Cases:** Future dates or extremely old dates might be data entry errors.
- **Human Reviewed:** No

### `encrypted_ssn`
- **Source Lineage:** `patient_records.ssn_enc`
- **Transformation Logic:** `ssn_enc`
- **Null Handling:** Pass through NULL values as NULL in the target column.
- **Edge Cases:** NULL values are allowed in the source table; values appear to be salted/hashed rather than standard reversible encryption.
- **Human Reviewed:** No

### `patient_status_code`
- **Source Lineage:** `patient_records.pat_st_cd`
- **Transformation Logic:** `CASE WHEN pat_st_cd IN ('A', 'D', 'S', 'I', 'Z') THEN pat_st_cd ELSE 'UNKNOWN' END`
- **Null Handling:** Treat invalid/special characters like '!' and '?' as NULL or map them to an 'UNKNOWN' status.
- **Edge Cases:** Contains unexpected/dirty values like '!' and '?'; ambiguous single-letter codes.
- **Human Reviewed:** Yes — Override Note: no changes made

### `insurance_plan_id`
- **Source Lineage:** `patient_records.plan_id`
- **Transformation Logic:** `plan_id`
- **Null Handling:** Preserve NULL values as NULL in the target warehouse.
- **Edge Cases:** Null rate is ~19.5%, which indicates some patients do not currently have an insurance plan or coverage associated with their record.
- **Human Reviewed:** No

### `created_at`
- **Source Lineage:** `patient_records.created_ts`
- **Transformation Logic:** `CAST(created_ts AS TIMESTAMP)`
- **Null Handling:** Allow NULLs as present in the source schema; default to current_timestamp() if appropriate for new records in the target.
- **Edge Cases:** Low cardinality (all records share the exact same timestamp in the sample, suggesting a potential backfill or batch import default).
- **Human Reviewed:** No

---

## Table: `providers`

### `prov_id`
- **Source Lineage:** `providers.prov_id`
- **Transformation Logic:** IDENTITY
- **Null Handling:** N/A (primary key, non-null)
- **Edge Cases:** None
- **Human Reviewed:** No

### `provider_name`
- **Source Lineage:** `providers.prov_nm`
- **Transformation Logic:** `TRIM(prov_nm)`
- **Null Handling:** Not applicable as null rate is 0.0 and column is NOT NULL.
- **Edge Cases:** Names may include titles like 'Dr.' which should be preserved or cleaned depending on warehouse conventions.
- **Human Reviewed:** No

### `provider_specialty_code`
- **Source Lineage:** `providers.prov_spec_cd`
- **Transformation Logic:** `UPPER(TRIM(prov_spec_cd))`
- **Null Handling:** Since the null rate is 0.0 and the column is NOT NULL, no null handling is strictly necessary beyond passing the value through.
- **Edge Cases:** Unknown specialty codes not present in the current sample set of 5 may appear if the table grows.
- **Human Reviewed:** No

### `is_active`
- **Source Lineage:** `providers.prov_active_flg`
- **Transformation Logic:** `CAST(prov_active_flg AS BOOLEAN)`
- **Null Handling:** Treat NULL as 0 (inactive) or filter depending on business requirements, though null rate is 0.0 so NULLs are not present in current sample.
- **Edge Cases:** None
- **Human Reviewed:** No

### `hire_date`
- **Source Lineage:** `providers.hire_dt`
- **Transformation Logic:** `CAST(hire_dt AS DATE)`
- **Null Handling:** Allow NULLs as present in the source; no default value needed.
- **Edge Cases:** None identified. Standard date field.
- **Human Reviewed:** No