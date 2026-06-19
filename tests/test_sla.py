import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sla import policy_for_severity


def test_critical_maps_to_p1_7_days():
    policy = policy_for_severity("Critical")

    assert policy.priority == "P1/Critical"
    assert policy.target == "7 days"
    assert policy.due_at is not None


def test_low_maps_to_p4_60_to_90_days():
    policy = policy_for_severity("Low")

    assert policy.priority == "P4/Low"
    assert policy.target == "60 - 90 days"
