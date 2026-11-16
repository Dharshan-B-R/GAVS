# Daily availability snapshots

Apply the Phase 2 Alembic migrations before enabling this job. The combined command records
the verified, unexpired saleable quantity for each active product in each active
shop, using that shop's configured IANA timezone. It is idempotent for a given
shop/product/local date and does not modify inventory.

Run from the `backend/` directory with the same environment variables as the API:

```bash
python -m scripts.run_daily_intelligence
```

Example cron schedule (runs daily at 23:55 server time):

```cron
55 23 * * * cd /path/to/GAVS/backend && /path/to/venv/bin/python -m scripts.run_daily_intelligence >> /var/log/kiranaai-intelligence.log 2>&1
```

Choose the schedule based on the deployment server timezone and operational
requirements. The combined job also generates shop-level daily summaries and refreshes deduplicated expiry, stockout and dead-stock alerts. The API also exposes a manual shop-scoped capture button in Flutter.
Do not run this command before all Phase 2 migrations for availability snapshots, alerts, daily summaries and feedback have been applied.
