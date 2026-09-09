"""
Seeds the legacy_db MySQL database with realistic, intentionally messy data.

Run AFTER `docker compose up -d` and after the container has applied
01_schema.sql (first boot only). Usage:

    pip install sqlalchemy pymysql faker python-dotenv
    python seed_db/seed_data.py

Produces:
  - insurance_plans   : 5 rows
  - providers         : 40 rows
  - patient_records   : 12,000 rows   (>10k required by the brief)
  - encounters        : 30,000 rows
  - billing_transactions : 34,000 rows

Deliberate messiness (mirrors what the profiler / AI mapper must handle):
  - status codes with no lookup table (pat_st_cd, enc_typ_cd, enc_st, txn_st_cd)
  - ~3% of encounters.pat_id / prov_id are NULL (broken legacy links)
  - ~1% of status codes are stray/unexpected values ('?', '', 'ZZ')
  - pmt_mthd_cd is NULL for ~15% of transactions (unknown payment method)
"""
import os
import random
from datetime import datetime, timedelta

from faker import Faker
from sqlalchemy import create_engine, text

fake = Faker()
random.seed(42)
Faker.seed(42)

DB_URL = os.environ.get(
    "SOURCE_DB_URL", "mysql+pymysql://legacy_user:legacy_pass@localhost:3306/legacy_db"
)

PLAN_TYPES = ["H", "P", "M", "X"]
SPEC_CODES = ["GEN", "CAR", "ORT", "PED", "ONC"]
PAT_STATUS = ["A", "D", "I", "S"]
PAT_STATUS_WEIGHTS = [0.55, 0.25, 0.15, 0.05]
ENC_TYPE = ["OV", "ER", "IP", "TC"]
ENC_STATUS = ["O", "C", "X"]
TXN_STATUS = ["P", "O", "R", "W"]
PAY_METHOD = ["CC", "CH", "CA", "IN"]

# STRAY_VALUES = ["?", "", "ZZ", " a", "d "] 
STRAY_VALUES = ["?", "Z", "!"] # dirty-data noise, ~1% injection rate


def maybe_dirty(value, rate=0.01):
    return random.choice(STRAY_VALUES) if random.random() < rate else value


def random_dt(start_year=2015, end_year=2025):
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    return start + timedelta(seconds=random.randint(0, int((end - start).total_seconds())))


def main():
    engine = create_engine(DB_URL, future=True)

    with engine.begin() as conn:
        print("Seeding insurance_plans...")
        plan_ids = []
        for i in range(5):
            res = conn.execute(
                text(
                    "INSERT INTO insurance_plans (plan_nm, plan_typ_cd, plan_active) "
                    "VALUES (:nm, :cd, :active)"
                ),
                {"nm": fake.company() + " Health Plan", "cd": PLAN_TYPES[i % len(PLAN_TYPES)], "active": 1},
            )
            plan_ids.append(res.lastrowid)

        print("Seeding providers...")
        prov_ids = []
        for _ in range(40):
            res = conn.execute(
                text(
                    "INSERT INTO providers (prov_nm, prov_spec_cd, prov_active_flg, hire_dt) "
                    "VALUES (:nm, :spec, :active, :hire)"
                ),
                {
                    "nm": "Dr. " + fake.last_name(),
                    "spec": random.choice(SPEC_CODES),
                    "active": random.choice([1, 1, 1, 0]),
                    "hire": fake.date_between(start_date="-15y", end_date="-1y"),
                },
            )
            prov_ids.append(res.lastrowid)

        print("Seeding patient_records (12,000 rows)...")
        pat_ids = []
        batch = []
        for _ in range(12000):
            batch.append(
                {
                    "fn": fake.first_name(),
                    "ln": fake.last_name(),
                    "dob": fake.date_of_birth(minimum_age=0, maximum_age=95),
                    "ssn": fake.sha256()[:60],  # stand-in for an "encrypted" blob
                    "st": maybe_dirty(random.choices(PAT_STATUS, PAT_STATUS_WEIGHTS)[0]),
                    "plan": random.choice(plan_ids + [None]) if random.random() < 0.97 else None,
                }
            )
        result = conn.execute(
            text(
                "INSERT INTO patient_records (pat_fname, pat_lname, dob, ssn_enc, pat_st_cd, plan_id) "
                "VALUES (:fn, :ln, :dob, :ssn, :st, :plan)"
            ),
            batch,
        )
        # fetch ids back (MySQL doesn't return per-row lastrowid on executemany reliably,
        # so pull them from the table)
        pat_ids = [r[0] for r in conn.execute(text("SELECT pat_id FROM patient_records")).fetchall()]

        print("Seeding encounters (30,000 rows)...")
        batch = []
        for _ in range(30000):
            pat_id = random.choice(pat_ids) if random.random() > 0.03 else None  # ~3% broken link
            prov_id = random.choice(prov_ids) if random.random() > 0.03 else None
            batch.append(
                {
                    "pat": pat_id,
                    "prov": prov_id,
                    "dt": random_dt(),
                    "typ": maybe_dirty(random.choice(ENC_TYPE)),
                    "amt": round(random.uniform(50, 5000), 2),
                    "st": maybe_dirty(random.choice(ENC_STATUS)),
                }
            )
        conn.execute(
            text(
                "INSERT INTO encounters (pat_id, prov_id, enc_dt, enc_typ_cd, enc_amt, enc_st) "
                "VALUES (:pat, :prov, :dt, :typ, :amt, :st)"
            ),
            batch,
        )
        enc_ids = [r[0] for r in conn.execute(text("SELECT enc_id FROM encounters")).fetchall()]

        print("Seeding billing_transactions (34,000 rows)...")
        batch = []
        for _ in range(34000):
            enc_id = random.choice(enc_ids) if random.random() > 0.02 else None
            batch.append(
                {
                    "enc": enc_id,
                    "amt": round(random.uniform(20, 5000), 2),
                    "st": maybe_dirty(random.choice(TXN_STATUS)),
                    "pmt": random.choice(PAY_METHOD) if random.random() > 0.15 else None,
                    "dt": random_dt(),
                }
            )
        conn.execute(
            text(
                "INSERT INTO billing_transactions (enc_id, txn_amt, txn_st_cd, pmt_mthd_cd, txn_dt) "
                "VALUES (:enc, :amt, :st, :pmt, :dt)"
            ),
            batch,
        )

    print("Done. Row counts:")
    with engine.connect() as conn:
        for tbl in ["insurance_plans", "providers", "patient_records", "encounters", "billing_transactions"]:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            print(f"  {tbl}: {n}")


if __name__ == "__main__":
    main()
