from repositories import SmtpRateLimitRepository


class SmtpRateLimiter:
    def __init__(
        self,
        repository: SmtpRateLimitRepository,
        max_per_minute: int,
        max_per_hour: int,
    ):
        self.repository = repository
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour

    def quota_available(self) -> bool:
        minute_count, hour_count = self.repository.current_counts()
        return minute_count < self.max_per_minute and hour_count < self.max_per_hour

    def record_send(
        self,
        *,
        finding_id: int,
        recipient_email: str,
        to_emails: str | None = None,
        cc_emails: str | None = None,
        flow_type: str | None = None,
        delivery_mode: str | None = None,
    ) -> None:
        self.repository.record_send(
            finding_id=finding_id,
            recipient_email=recipient_email,
            to_emails=to_emails,
            cc_emails=cc_emails,
            flow_type=flow_type,
            delivery_mode=delivery_mode,
        )
