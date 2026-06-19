import smtplib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from retry import is_transient_smtp_error, retry_delay_seconds


def test_retry_delay_uses_exponential_backoff():
    assert retry_delay_seconds(
        attempt_number=1,
        base_delay_seconds=60,
        backoff_multiplier=2,
    ) == 60
    assert retry_delay_seconds(
        attempt_number=2,
        base_delay_seconds=60,
        backoff_multiplier=2,
    ) == 120


def test_smtp_4xx_is_transient_and_5xx_is_not():
    assert is_transient_smtp_error(smtplib.SMTPResponseException(421, b"try later"))
    assert not is_transient_smtp_error(smtplib.SMTPResponseException(550, b"bad recipient"))
