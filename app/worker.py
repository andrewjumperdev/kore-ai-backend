"""Worker entrypoint for Dramatiq.

Run with:  dramatiq app.worker

Importing this module sets the Redis broker and pulls in every actor module so
Dramatiq discovers them. The scheduler role (KORE_ROLE=scheduler) schedules the
daily orchestrator sweep (§05/§08) and the monthly MRR invoicing.
"""
from __future__ import annotations

import os

from app.core.logging import configure_logging, get_logger

# Broker first — actors register against it on import.
from app.tasks.broker import redis_broker  # noqa: F401
from app.tasks import (  # noqa: F401  (import to register actors)
    agent_tasks,
    billing_tasks,
    customer_service_tasks,
    event_tasks,
    followup_tasks,
    orchestrator_tasks,
    prospecting_tasks,
)

configure_logging(debug=os.getenv("KORE_DEBUG", "false").lower() == "true")
log = get_logger("worker")
log.info("worker.ready")


def start_scheduler() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    from app.tasks.billing_tasks import open_all_period_invoices
    from app.tasks.orchestrator_tasks import run_all_orchestrator_sweeps
    from app.tasks.prospecting_tasks import run_prospecting_all

    scheduler = BlockingScheduler(timezone="UTC")
    # Cold email: un batch por tenant cada hora (como el trigger del n8n).
    scheduler.add_job(
        lambda: run_prospecting_all.send(),
        CronTrigger(minute=0),
        id="hourly_prospecting",
    )
    # Daily supervisor sweep: stale pipeline, overcontacted leads, metrics/alerts.
    scheduler.add_job(
        lambda: run_all_orchestrator_sweeps.send(),
        CronTrigger(hour=7, minute=0),
        id="daily_orchestrator_sweep",
    )
    # Monthly MRR invoicing.
    scheduler.add_job(
        lambda: open_all_period_invoices.send(),
        CronTrigger(day=1, hour=3, minute=0),
        id="monthly_mrr_invoicing",
    )
    log.info("scheduler.start")
    scheduler.start()


if __name__ == "__main__" and os.getenv("KORE_ROLE") == "scheduler":
    start_scheduler()
