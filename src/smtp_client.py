import smtplib
from email.message import EmailMessage

from config import Settings
from schemas import EmailPayload


class SmtpClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, payload: EmailPayload) -> None:
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
