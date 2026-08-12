"""
مولّد مجموعات البيانات التجريبية - Demo Dataset Generator
Generates 5 CSV files with realistic survey data, enriched fields, and controlled inconsistencies.

Output files:
  1) demo_clean.csv       — mostly valid data (~90% clean)
  2) demo_flagged.csv     — heavily inconsistent (~70% flagged)
  3) demo_mixed.csv       — realistic mix (~35% flagged)
  4) demo_fast.csv        — 25 rows for quick testing
  5) large_demo_5000.csv  — 5000 rows stress test
"""
import csv
import random
import os

SEED = 2024
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "demo")

REGIONS = ["Riyadh", "Jeddah", "Dammam"]
EDUCATIONS = ["High School", "Diploma", "Bachelor", "Master", "PhD"]
STATUSES = ["Full-time", "Part-time", "Unemployed", "Student", "Self-employed"]
QUESTION_IDS = [f"Q{i}" for i in range(1, 11)]

JOBS_BY_EDU = {
    "High School": ["Cashier", "Driver", "Security Guard", "Clerk", "Worker", "Janitor", "Waiter"],
    "Diploma": ["Technician", "Administrative Assistant", "Nurse", "Lab Technician", "Receptionist"],
    "Bachelor": ["Software Developer", "Accountant", "Teacher", "Designer", "Analyst", "Marketing Specialist", "HR Officer"],
    "Master": ["Senior Engineer", "Project Manager", "Consultant", "Researcher", "Data Scientist", "Financial Analyst"],
    "PhD": ["Professor", "Scientist", "Research Director", "Senior Researcher", "Department Head"],
}

INCOME_RANGES = {
    "High School": (3000, 8000),
    "Diploma": (5000, 12000),
    "Bachelor": (8000, 25000),
    "Master": (15000, 40000),
    "PhD": (25000, 70000),
}

EDU_MIN_AGE = {"High School": 18, "Diploma": 20, "Bachelor": 22, "Master": 25, "PhD": 28}

FIELDNAMES = [
    "age", "experience_years", "education", "job_title",
    "income", "region", "employment_status", "enumerator_id", "question_id"
]


def _make_clean_row(rng: random.Random, enumerator_id: str = None) -> dict:
    """Generate a logically consistent row."""
    edu = rng.choice(EDUCATIONS)
    min_age = EDU_MIN_AGE[edu]
    age = rng.randint(min_age, min_age + 30)
    max_exp = max(0, age - 18)
    exp = rng.randint(0, max_exp)
    job = rng.choice(JOBS_BY_EDU[edu])
    lo, hi = INCOME_RANGES[edu]
    income = rng.randint(lo, hi)
    status = rng.choices(["Full-time", "Part-time", "Self-employed"], weights=[70, 15, 15])[0]
    region = rng.choice(REGIONS)
    enum_id = enumerator_id or f"E{rng.randint(1, 15):03d}"
    q_id = rng.choice(QUESTION_IDS)

    return {
        "age": age, "experience_years": exp, "education": edu,
        "job_title": job, "income": income, "region": region,
        "employment_status": status, "enumerator_id": enum_id,
        "question_id": q_id,
    }


def _inject_rule_issue(row: dict, rng: random.Random, issue_type: str) -> dict:
    """Inject a rule-based inconsistency."""
    r = dict(row)
    if issue_type == "young_age":
        r["age"] = rng.randint(12, 17)
    elif issue_type == "old_age":
        r["age"] = rng.randint(71, 95)
    elif issue_type == "exp_gt_age":
        r["experience_years"] = r["age"] + rng.randint(5, 20)
    elif issue_type == "missing_income":
        r["income"] = 0
    elif issue_type == "duplicate_pattern":
        # Make enumerator suspicious
        r["enumerator_id"] = "E001"
        r["age"] = 30
        r["experience_years"] = 5
    return r


def _inject_semantic_issue(row: dict, rng: random.Random, issue_type: str) -> dict:
    """Inject a semantic/logical inconsistency."""
    r = dict(row)
    if issue_type == "phd_low_job":
        r["education"] = "PhD"
        r["job_title"] = rng.choice(["Cashier", "Janitor", "Waiter", "Security Guard"])
        r["income"] = rng.randint(3000, 7000)
    elif issue_type == "unemployed_high_income":
        r["employment_status"] = "Unemployed"
        r["income"] = rng.randint(30000, 90000)
    elif issue_type == "job_edu_mismatch":
        r["education"] = rng.choice(["High School", "Diploma"])
        r["job_title"] = rng.choice(["Professor", "Scientist", "Surgeon", "Research Director"])
        r["income"] = rng.randint(40000, 80000)
    elif issue_type == "student_high_exp":
        r["employment_status"] = "Student"
        r["age"] = rng.randint(18, 22)
        r["experience_years"] = rng.randint(10, 25)
    elif issue_type == "young_phd":
        r["education"] = "PhD"
        r["age"] = rng.randint(18, 24)
        r["job_title"] = rng.choice(["Professor", "Senior Researcher"])
        r["income"] = rng.randint(50000, 80000)
    return r


RULE_ISSUES = ["young_age", "old_age", "exp_gt_age", "missing_income", "duplicate_pattern"]
SEMANTIC_ISSUES = ["phd_low_job", "unemployed_high_income", "job_edu_mismatch", "student_high_exp", "young_phd"]


def generate_dataset(n_rows: int, error_rate: float, rng: random.Random, skew_semantic: float = 0.5) -> list[dict]:
    """
    Generate n_rows with approximately error_rate fraction of rows having issues.
    skew_semantic controls ratio of semantic vs rule issues (0.5 = balanced).
    """
    rows = []
    enumerators = [f"E{i:03d}" for i in range(1, 16)]

    for i in range(n_rows):
        enum_id = rng.choice(enumerators)
        row = _make_clean_row(rng, enum_id)

        if rng.random() < error_rate:
            if rng.random() < skew_semantic:
                issue = rng.choice(SEMANTIC_ISSUES)
                row = _inject_semantic_issue(row, rng, issue)
            else:
                issue = rng.choice(RULE_ISSUES)
                row = _inject_rule_issue(row, rng, issue)

        rows.append(row)
    return rows


def write_csv(rows: list[dict], filepath: str):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  ✅ {os.path.basename(filepath)}: {len(rows)} rows")


def generate_template(filepath: str):
    """Generate an empty CSV template with headers only."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
    print(f"  ✅ {os.path.basename(filepath)}: template (headers only)")


def main():
    print("🔧 Generating demo CSV files...")

    # Template
    generate_template(os.path.join(OUTPUT_DIR, "survey_template.csv"))

    # 1) demo_clean.csv — ~90% clean, 50 rows
    rng1 = random.Random(SEED)
    rows_clean = generate_dataset(50, 0.10, rng1)
    write_csv(rows_clean, os.path.join(OUTPUT_DIR, "demo_clean.csv"))

    # 2) demo_flagged.csv — ~70% flagged, 50 rows
    rng2 = random.Random(SEED + 1)
    rows_flagged = generate_dataset(50, 0.70, rng2, skew_semantic=0.6)
    write_csv(rows_flagged, os.path.join(OUTPUT_DIR, "demo_flagged.csv"))

    # 3) demo_mixed.csv — ~35% flagged, 100 rows
    rng3 = random.Random(SEED + 2)
    rows_mixed = generate_dataset(100, 0.35, rng3)
    write_csv(rows_mixed, os.path.join(OUTPUT_DIR, "demo_mixed.csv"))

    # 4) demo_fast.csv — 25 rows quick test
    rng4 = random.Random(SEED + 3)
    rows_fast = generate_dataset(25, 0.30, rng4)
    write_csv(rows_fast, os.path.join(OUTPUT_DIR, "demo_fast.csv"))

    # 5) large_demo_5000.csv — 5000 rows stress test
    rng5 = random.Random(SEED + 4)
    rows_large = generate_dataset(5000, 0.35, rng5, skew_semantic=0.55)
    write_csv(rows_large, os.path.join(OUTPUT_DIR, "large_demo_5000.csv"))

    print(f"\n✅ All files generated in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
