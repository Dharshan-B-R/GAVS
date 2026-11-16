"""Daily scheduled KiranaAI intelligence job.

Run after Alembic migrations are applied:
    python -m scripts.run_daily_intelligence
"""
from app.database import SessionLocal
from app.services.daily_intelligence_service import generate_all_daily_summaries
from scripts.capture_daily_availability import capture_all_shops


def run() -> dict:
    availability = capture_all_shops()
    db = SessionLocal()
    try:
        summaries = generate_all_daily_summaries(db)
    finally:
        db.close()
    return {"availability": availability, "summaries": summaries}


if __name__ == "__main__":
    result = run()
    print(result)
    if result["availability"]["failed_shops"] or result["summaries"]["failed"]:
        raise SystemExit(1)
