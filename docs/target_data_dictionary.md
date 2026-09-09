# Data Dictionary

## Table: `billing_transactions`

### `txn_id`
- **Source Lineage:** `billing_transactions.txn_id`
- **Transformation Logic:** IDENTITY
- **Null Handling:** N/A (primary key, non-null)
- **Edge Cases:** None
- **Human Review:** No

### `encounter_id`
- **Source Lineage:** `billing_transactions.enc_id`
- **Transformation Logic:** Cast to integer (`CAST(enc_id AS INTEGER)`)
- **Null Handling:** Preserve NULLs or map to a default sentinel value (e.g., -1) if an explicit foreign key placeholder is required by the target warehouse schema.
- **Edge Cases:** 1.93% of records have NULL enc_id, which may indicate offline or unassociated encounters; Integer IDs could potentially collide or re-sequence if consolidating multiple legacy databases.
- **Human Review:** No

### `transaction_amount`
- **Source Lineage:** `billing_transactions.txn_amt`
- **Transformation Logic:** Pass through value (`txn_amt`)
- **Null Handling:** Column is NOT NULL (null rate 0.0), so no null handling required.
- **Edge Cases:** Check for potential negative values if refunds or chargebacks exist, though samples are all positive.
- **Human Review:** No

### `transaction_status_code`
- **Source Lineage:** `billing_transactions.txn_st_cd`
- **Transformation Logic:** Conditional mapping via CASE statement (`CASE txn_st_cd WHEN 'P' then 'PROCESSED' WHEN 'W' THEN 'WAITING' WHEN 'R' THEN 'REJECTED' WHEN 'O' THEN 'OTHER' WHEN 'Z' THEN 'UNKNOWN' ELSE 'INVALID' END`)
- **Null Handling:** NOT NULL constraint exists, so default/fallback value needed for invalid/garbage codes.
- **Edge Cases:** Contains garbage/corrupted values like '?' and '!'; Undocumented single-letter codes ('W', 'R', 'P', 'O', 'Z') without a reference dictionary.
- **Human Review:** Yes (Override Note: testing for pipeline error)

### `payment_method_code`
- **Source Lineage:** `billing_transactions.pmt_mthd_cd`
- **Transformation Logic:** Convert to uppercase and trim whitespace (`UPPER(TRIM(pmt_mthd_cd))`)
- **Null Handling:** Preserve NULLs as NULL in the target warehouse column.
- **Edge Cases:** NULL values representing unknown or unpaid transactions (15.18% null rate).
- **Human Review:** No

### `transaction_timestamp`
- **Source Lineage:** `billing_transactions.txn_dt`
- **Transformation Logic:** Cast to timestamp (`CAST(txn_dt AS TIMESTAMP)`)
- **Null Handling:** Column is NOT NULL; no null handling needed. Cast directly to TIMESTAMP or equivalent warehouse datetime type.
- **Edge Cases:** None.
- **Human Review:** No

---

## Table: `encounters`

### `enc_id`
- **Source Lineage:** `encounters.enc_id`
- **Transformation Logic:** IDENTITY
- **Null Handling:** N/A (primary key, non-null)
- **Edge Cases:** None.
- **Human Review:** No

### `patient_id`
- **Source Lineage:** `encounters.pat_id`
- **Transformation Logic:** Pass through value (`pat_id`)
- **Null Handling:** Preserve NULLs or apply standard orphan handling strategy based on data warehouse constraints (e.g., allow NULL or map to a default -1 unknown patient record).
- **Edge Cases:** Null rate is ~3%, meaning some encounters might not be linked to a patient record (orphaned records or unassigned encounters).
- **Human Review:** No

### `provider_id`
- **Source Lineage:** `encounters.prov_id`
- **Transformation Logic:** Cast to integer (`CAST(prov_id AS INTEGER)`)
- **Null Handling:** Allow NULLs; preserve as NULL in target or map to a default unknown provider ID if required by dimensional modeling rules.
- **Edge Cases:** Null values represent unassigned or unknown providers (handle as NULL in target).
- **Human Review:** No

### `encounter_timestamp`
- **Source Lineage:** `encounters.enc_dt`
- **Transformation Logic:** Cast to timestamp (`CAST(enc_dt AS TIMESTAMP)`)
- **Null Handling:** Column is NOT NULL; no null handling needed.
- **Edge Cases:** Timezone info is not present in the datetime objects, might need normalization to UTC depending on warehouse standards.
- **Human Review:** No

### `encounter_type_code`
- **Source Lineage:** `encounters.enc_typ_cd`
- **Transformation Logic:** Conditional mapping to filter out sentinel values (`CASE WHEN enc_typ_cd IN ('?', '!', 'Z') THEN NULL ELSE enc_typ_cd END`)
- **Null Handling:** Since nullable is False, invalid/unknown values are captured via sentinel characters like '?', '!', or 'Z'. These should be mapped to a standardized NULL or 'UNKNOWN' value in the target warehouse.
- **Edge Cases:** Data quality issues present with sentinel values 'Z', '?', and '!' representing unknown, invalid, or missing codes.
- **Human Review:** No

### `encounter_amount`
- **Source Lineage:** `encounters.enc_amt`
- **Transformation Logic:** Cast to decimal (`CAST(enc_amt AS DECIMAL(10, 2))`)
- **Null Handling:** Keep NULLs as NULL if encountered in future rows (currently 0% null rate).
- **Edge Cases:** Negative values or zero might exist beyond the sample set, though not shown in the samples.
- **Human Review:** No

### `encounter_status_code`
- **Source Lineage:** `encounters.enc_st`
- **Transformation Logic:** Conditional mapping via CASE statement (`CASE enc_st WHEN 'C' THEN 'COMPLETED' WHEN 'O' THEN 'OPEN' WHEN 'X' THEN 'CANCELLED' ELSE 'UNKNOWN' END`)
- **Null Handling:** Since null rate is 0.0, no null handling is strictly required by data, but an 'UNKNOWN' or 'OTHER' fallback should be considered for invalid codes.
- **Edge Cases:** Sample values contain unexpected characters like '!', '?', and 'Z' which do not fit standard encounter state/status workflows; Values 'C' and 'O' likely mean Closed/Open or Completed/Ongoing, but 'X', 'Z', '!', '?' are ambiguous without a domain data dictionary.
- **Human Review:** Yes (Override Note: teasting for pipeline error)

---

## Table: `insurance_plans`

### `plan_id`
- **Source Lineage:** `insurance_plans.plan_id`
- **Transformation Logic:** IDENTITY
- **Null Handling:** N/A (primary key, non-null)
- **Edge Cases:** None.
- **Human Review:** No

### `plan_name`
- **Source Lineage:** `insurance_plans.plan_nm`
- **Transformation Logic:** Trim whitespace (`TRIM(plan_nm)`)
- **Null Handling:** Column is NOT NULL; pass through existing values or apply standard string trimming.
- **Edge Cases:** None identified.
- **Human Review:** No

### `plan_type_code`
- **Source Lineage:** `insurance_plans.plan_typ_cd`
- **Transformation Logic:** Conditional mapping via CASE statement (`CASE plan_typ_cd WHEN 'H' THEN 'HMO' WHEN 'P' THEN 'PPO' WHEN 'M' THEN 'MEDICARE_MEDICAID' ELSE 'UNKNOWN' END`)
- **Null Handling:** Since nullable is false, no NULL handling is needed beyond a default/fallback if invalid codes appear.
- **Edge Cases:** Unknown 'X' code could cause validation errors in downstream strict enums.
- **Human Review:** No

### `is_plan_active`
- **Source Lineage:** `insurance_plans.plan_active`
- **Transformation Logic:** Cast to boolean (`CAST(plan_active AS BOOLEAN)`)
- **Null Handling:** Default to 1 or TRUE if nullable in source and missing, otherwise preserve NULL if not strictly required to be boolean.
- **Edge Cases:** Cardinality is 1 in the sample data (only value is 1), so while the name and type strongly indicate a boolean/status flag, all rows in this particular sample set are currently active (1).
- **Human Review:** No

---

## Table: `patient_records`

### `pat_id`
- **Source Lineage:** `patient_records.pat_id`
- **Transformation Logic:** IDENTITY
- **Null Handling:** N/A (primary key, non-null)
- **Edge Cases:** None.
- **Human Review:** No

### `first_name`
- **Source Lineage:** `patient_records.pat_fname`
- **Transformation Logic:** Trim whitespace (`TRIM(pat_fname)`)
- **Null Handling:** Column is NOT NULL; pass through values directly (possibly with trim).
- **Edge Cases:** Names with unusual characters, hyphenated names, or trailing spaces (though samples are clean).
- **Human Review:** No

### `last_name`
- **Source Lineage:** `patient_records.pat_lname`
- **Transformation Logic:** Trim whitespace (`TRIM(pat_lname)`)
- **Null Handling:** NOT NULL column; pass through directly or trim whitespace.
- **Edge Cases:** Names with special characters, apostrophes, or hyphens (though none appear in the samples).
- **Human Review:** No

### `date_of_birth`
- **Source Lineage:** `patient_records.dob`
- **Transformation Logic:** Cast to date (`CAST(dob AS DATE)`)
- **Null Handling:** Allow NULLs as present in the source table (null_rate is 0.0, but nullable is True).
- **Edge Cases:** Dates in the future might be data entry errors, though valid up to current date; Patients over ~120 years old may indicate legacy data artifacts.
- **Human Review:** No

### `ssn_hash`
- **Source Lineage:** `patient_records.ssn_enc`
- **Transformation Logic:** Cast to varchar (`CAST(ssn_enc AS VARCHAR(120))`)
- **Null Handling:** Preserve NULLs if present in source data.
- **Edge Cases:** Missing/null values are allowed in the schema (0.0 null rate observed here, but nullable), though none appear in the sample; Data is already hashed/encrypted at rest in the legacy system.
- **Human Review:** No

### `patient_status_code`
- **Source Lineage:** `patient_records.pat_st_cd`
- **Transformation Logic:** Conditional validation via CASE statement (`CASE WHEN pat_st_cd IN ('A', 'D', 'S', 'I', 'Z') THEN pat_st_cd ELSE 'UNKNOWN' END`)
- **Null Handling:** Not nullable (Null rate: 0.0), but invalid codes ('!', '?') should likely be mapped to NULL or an 'UNKNOWN' category in the target warehouse.
- **Edge Cases:** Contains invalid/corrupted values like '!', '?', and 'Z'; Standard US state codes would not include '!', '?', or have a cardinality of 7 for patient records.
- **Human Review:** Yes (Override Note: testing for pipeline error)

### `insurance_plan_id`
- **Source Lineage:** `patient_records.plan_id`
- **Transformation Logic:** Pass through value (`plan_id`)
- **Null Handling:** Preserve NULLs as they represent patients without an associated insurance plan on record.
- **Edge Cases:** 19.5% null rate indicates patients who may not have an active insurance plan or are self-pay.
- **Human Review:** No

### `created_at`
- **Source Lineage:** `patient_records.created_ts`
- **Transformation Logic:** Cast to timestamp (`CAST(created_ts AS TIMESTAMP)`)
- **Null Handling:** Allow NULL since the column is nullable, though null rate is currently 0.0.
- **Edge Cases:** Constant value in sample, check if future date (2026) is a data entry artifact.
- **Human Review:** No

---

## Table: `providers`

### `prov_id`
- **Source Lineage:** `providers.prov_id`
- **Transformation Logic:** IDENTITY
- **Null Handling:** N/A (primary key, non-null)
- **Edge Cases:** None.
- **Human Review:** No

### `provider_name`
- **Source Lineage:** `providers.prov_nm`
- **Transformation Logic:** Trim whitespace (`TRIM(prov_nm)`)
- **Null Handling:** NOT NULL, pass through directly as string.
- **Edge Cases:** Titles like 'Dr.' are included in the name string; Names may contain special characters or spaces.
- **Human Review:** No

### `provider_specialty_code`
- **Source Lineage:** `providers.prov_spec_cd`
- **Transformation Logic:** Convert to uppercase and trim whitespace (`UPPER(TRIM(prov_spec_cd))`)
- **Null Handling:** Since the column is NOT NULL, preserve as NOT NULL in the target. If invalid/missing states are encountered during loads, map to 'UNK' or handle via default constraint.
- **Edge Cases:** Unknown codes not present in the current set of 5 sample values might appear in future loads.
- **Human Review:** No

### `is_active`
- **Source Lineage:** `providers.prov_active_flg`
- **Transformation Logic:** Cast to boolean (`CAST(prov_active_flg AS BOOLEAN)`)
- **Null Handling:** Treat NULL as inactive (0) or keep as NULL depending on warehouse conventions; here null rate is 0.0 so NULLs are not present in the sample data.
- **Edge Cases:** None identified.
- **Human Review:** No

### `hire_date`
- **Source Lineage:** `providers.hire_dt`
- **Transformation Logic:** Cast to date (`CAST(hire_dt AS DATE)`)
- **Null Handling:** Allow NULLs as present in source, though null rate is currently 0.0.
- **Edge Cases:** None observed; standard date format with zero nulls.
- **Human Review:** No