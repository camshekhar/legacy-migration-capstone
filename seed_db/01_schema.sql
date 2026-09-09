-- =====================================================================
-- Legacy schema: fictional healthcare/billing OLTP system.
-- Intentionally messy: inconsistent naming, undocumented status codes,
-- nullable FKs, zero column comments -- this is the point of the capstone.
-- =====================================================================

USE legacy_db;

CREATE TABLE insurance_plans (
    plan_id       INT AUTO_INCREMENT PRIMARY KEY,
    plan_nm       VARCHAR(100) NOT NULL,
    plan_typ_cd   VARCHAR(2)   NOT NULL,   -- undocumented: 'H'=HMO,'P'=PPO,'M'=Medicare,'X'=Self-pay
    plan_active   TINYINT(1)   DEFAULT 1
);

CREATE TABLE providers (
    prov_id        INT AUTO_INCREMENT PRIMARY KEY,
    prov_nm        VARCHAR(120) NOT NULL,
    prov_spec_cd   VARCHAR(3)   NOT NULL,  -- undocumented: 'GEN','CAR','ORT','PED','ONC'
    prov_active_flg TINYINT(1)  DEFAULT 1,
    hire_dt        DATE
);

CREATE TABLE patient_records (
    pat_id        INT AUTO_INCREMENT PRIMARY KEY,
    pat_fname     VARCHAR(60)  NOT NULL,
    pat_lname     VARCHAR(60)  NOT NULL,
    dob           DATE,
    ssn_enc       VARCHAR(120),            -- sensitive: pretend-encrypted SSN blob
    pat_st_cd     VARCHAR(2)   NOT NULL,   -- undocumented status: 'A'=Active,'D'=Discharged,'I'=Inactive,'S'=Suspended
    plan_id       INT NULL,
    created_ts    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_pat_plan FOREIGN KEY (plan_id) REFERENCES insurance_plans(plan_id)
);

CREATE TABLE encounters (
    enc_id        INT AUTO_INCREMENT PRIMARY KEY,
    pat_id        INT NULL,               -- nullable FK: some legacy rows never linked correctly
    prov_id       INT NULL,
    enc_dt        DATETIME NOT NULL,
    enc_typ_cd    VARCHAR(2) NOT NULL,    -- undocumented: 'OV'=Office Visit,'ER'=Emergency,'IP'=Inpatient,'TC'=Telehealth
    enc_amt       DECIMAL(10,2),
    enc_st        VARCHAR(1) NOT NULL,    -- undocumented: 'O'=Open,'C'=Closed,'X'=Cancelled
    CONSTRAINT fk_enc_pat  FOREIGN KEY (pat_id)  REFERENCES patient_records(pat_id),
    CONSTRAINT fk_enc_prov FOREIGN KEY (prov_id) REFERENCES providers(prov_id)
);

CREATE TABLE billing_transactions (
    txn_id        INT AUTO_INCREMENT PRIMARY KEY,
    enc_id        INT NULL,
    txn_amt       DECIMAL(10,2) NOT NULL,
    txn_st_cd     VARCHAR(1) NOT NULL,    -- undocumented: 'P'=Paid,'O'=Outstanding,'R'=Refunded,'W'=Write-off
    pmt_mthd_cd   VARCHAR(2),             -- undocumented: 'CC','CH'(check),'CA'(cash),'IN'(insurance), NULL=unknown
    txn_dt        DATETIME NOT NULL,
    CONSTRAINT fk_txn_enc FOREIGN KEY (enc_id) REFERENCES encounters(enc_id)
);

CREATE INDEX idx_enc_pat ON encounters(pat_id);
CREATE INDEX idx_enc_prov ON encounters(prov_id);
CREATE INDEX idx_txn_enc ON billing_transactions(enc_id);
CREATE INDEX idx_pat_plan ON patient_records(plan_id);
