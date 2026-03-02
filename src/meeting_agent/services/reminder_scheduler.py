import logging
from datetime import datetime
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger(__name__)
ReminderCallback = Callable[[str, str, datetime], None]


class ReminderScheduler:
    def __init__(self, callback: Optional[ReminderCallback] = None) -> None:
        self._scheduler = BackgroundScheduler()
        self._callback = callback or self._default_callback
        self._started = False

    @staticmethod
    def _default_callback(booking_id: str, title: str, start_time: datetime) -> None:
        logger.info("提醒: 会议 [%s] 即将开始，开始时间 %s", title, start_time.isoformat())

    def start(self) -> None:
        if not self._started:
            self._scheduler.start()
            self._started = True
            logger.info("ReminderScheduler started")

    def shutdown(self, wait: bool = True) -> None:
        self._scheduler.shutdown(wait=wait)
        self._started = False

    def schedule_reminder(
        self,
        run_at: datetime,
        booking_id: str,
        title: str,
        start_time: datetime,
    ) -> str:
        self.start()
        job = self._scheduler.add_job(
            self._fire_reminder,
            trigger=DateTrigger(run_date=run_at),
            args=[booking_id, title, start_time],
            id=booking_id,
            replace_existing=True,
        )
        logger.info("已安排提醒 job_id=%s at %s", job.id, run_at.isoformat())
        return job.id

    def _fire_reminder(self, booking_id: str, title: str, start_time: datetime) -> None:
        try:
            self._callback(booking_id, title, start_time)
        except Exception as e:
            logger.exception("提醒回调异常: %s", e)

    def cancel_reminder(self, job_id: str) -> bool:
        try:
            self._scheduler.remove_job(job_id)
            return True
        except Exception as e:
            logger.warning("取消提醒失败 %s: %s", job_id, e)
            return False
