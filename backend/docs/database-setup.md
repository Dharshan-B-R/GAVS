# KiranaAI database setup

## Brand-new, empty database

1. Create an empty PostgreSQL database.
2. Configure `DATABASE_URL` for that database using the same environment configuration as the backend.
3. From the repository root, run:

```powershell
python backend/scripts/bootstrap_fresh_database.py
```

The bootstrap imports the FastAPI application so all current SQLAlchemy models are registered, creates the current schema with `Base.metadata.create_all()`, then stamps Alembic at the current head. This avoids replaying historical migrations that were written against the pre-existing legacy schema.

**Only use this command on a truly empty database.** It is not a migration or reset command. It must never be run against an existing or populated database.

## Existing KiranaAI database

From the `backend` directory, configure the existing database URL and run:

```powershell
alembic current
alembic upgrade head
alembic current
```

The current revision should be `a7c3e9f1b620`. If the database is unversioned or reports a different revision, stop and inspect its schema and data before stamping or upgrading. Do not guess a revision and do not drop tables.

## Schema maintenance

- Alembic migrations remain the source of truth for changes after the current head.
- SQLAlchemy models declare the same employee job-role and supplier-status check constraints as the existing migration.
- Application startup's `create_all()` is not a substitute for applying migrations to an existing database.
- Take a database backup before applying migrations to a non-disposable database.
