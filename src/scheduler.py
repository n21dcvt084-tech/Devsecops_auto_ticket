import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from config import Settings
from database import get_session_factory
from processor import FindingProcessor

logger = logging.getLogger(__name__)


class AppScheduler:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.scheduler = BackgroundScheduler(timezone="UTC")

    def start(self) -> None:
        self.scheduler.add_job(
            self._run_cycle,
            "interval",
            seconds=self.settings.scheduler_interval_seconds,
            id="defectdojo_polling_job",
            max_instances=1,
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc),
        )
        self.scheduler.start()
        logger.info("Scheduler start")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler end")

    def is_running(self) -> bool:
        return self.scheduler.running

    def _run_cycle(self) -> None:
        db = get_session_factory()()
        try:
            processor = FindingProcessor(self.settings, db)
            processor.process_scheduler_cycle()
        finally:
            db.close()
