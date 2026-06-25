"""Build and send SMTP messages and classify retryable transport errors."""

import smtplib
import socket
from email.message import EmailMessage

from config import Settings
from schemas import EmailPayload


def retry_delay_seconds(
    *,
    attempt_number: int,
    base_delay_seconds: int,
    backoff_multiplier: int,
) -> int:
    """Calculate exponential retry delay for the supplied attempt number."""
    return base_delay_seconds * (backoff_multiplier ** max(attempt_number - 1, 0))


def is_transient_smtp_error(error: Exception) -> bool:
    """Return whether an SMTP/network error is safe to retry."""
    if isinstance(error, (TimeoutError, socket.timeout, ConnectionResetError)):
        return True
    if isinstance(error, smtplib.SMTPServerDisconnected):
        return True
    if isinstance(error, smtplib.SMTPConnectError):
        return True
    if isinstance(error, smtplib.SMTPResponseException):
        return 400 <= error.smtp_code < 500
    return False


class SmtpClient:
    """Send multipart messages through authenticated SMTP with optional TLS."""

    def __init__(self, settings: Settings):
        """Store SMTP connection and sender settings."""
        self.settings = settings

    def send(self, payload: EmailPayload) -> None:
        """Build one EmailMessage from the payload and submit it to SMTP."""
        message = EmailMessage()
        message["From"] = self.settings.smtp_from_email
        to_recipients = [str(payload.recipient_email)]
        to_recipients.extend(str(email) for email in payload.to_emails)
        message["To"] = ", ".join(dict.fromkeys(to_recipients))
        if payload.cc_emails:
            message["Cc"] = ", ".join(str(email) for email in payload.cc_emails)
        message["Subject"] = payload.subject
        message.set_content(payload.body)
        if payload.html_body:
            message.add_alternative(payload.html_body, subtype="html")

        with smtplib.SMTP(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=self.settings.smtp_timeout_seconds,
        ) as smtp:
            if self.settings.smtp_use_tls:
                smtp.starttls()
            if self.settings.smtp_username and self.settings.smtp_password:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(message)
