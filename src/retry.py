import smtplib
import socket


def retry_delay_seconds(
    *,
    attempt_number: int,
    base_delay_seconds: int,
    backoff_multiplier: int,
) -> int:
    return base_delay_seconds * (backoff_multiplier ** max(attempt_number - 1, 0))


def is_transient_smtp_error(error: Exception) -> bool:
    if isinstance(error, (TimeoutError, socket.timeout, ConnectionResetError)):
        return True
    if isinstance(error, smtplib.SMTPServerDisconnected):
        return True
    if isinstance(error, smtplib.SMTPConnectError):
        return True
    if isinstance(error, smtplib.SMTPResponseException):
        return 400 <= error.smtp_code < 500
    return False
