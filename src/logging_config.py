import logging
import sys


class ContextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = {
            "finding_id": getattr(record, "finding_id", None),
            "product": getattr(record, "product", None),
            "severity": getattr(record, "severity", None),
            "recipient_email": getattr(record, "recipient_email", None),
            "dedupe_key": getattr(record, "dedupe_key", None),
            "ticket_id": getattr(record, "ticket_id", None),
            "missing_fields": getattr(record, "missing_fields", None),
            "status": getattr(record, "status", None),
            "error_message": getattr(record, "error_message", None),
        }
        context = " ".join(
            f"{key}={value}" for key, value in fields.items() if value is not None
        )
        message = super().format(record)
        if context:
            return f"{message} {context}"
        return message


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        ContextFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
