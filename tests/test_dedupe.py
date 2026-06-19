import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dedupe import build_dedupe_key
from schemas import DefectDojoFinding


def test_same_web_issue_gets_same_dedupe_key_even_with_different_finding_id():
    first = DefectDojoFinding(
        finding_id=100,
        title="SQL Injection",
        severity="Critical",
        product="Customer Portal",
        endpoint="app.example.com/login",
        parameter="username",
    )
    second = DefectDojoFinding(
        finding_id=200,
        title="SQL Injection",
        severity="Critical",
        product="Customer Portal",
        endpoint="app.example.com/login",
        parameter="username",
    )

    assert build_dedupe_key(first) == build_dedupe_key(second)


def test_different_endpoint_gets_different_dedupe_key():
    first = DefectDojoFinding(
        finding_id=100,
        title="SQL Injection",
        severity="Critical",
        product="Customer Portal",
        endpoint="app.example.com/login",
    )
    second = DefectDojoFinding(
        finding_id=200,
        title="SQL Injection",
        severity="Critical",
        product="Customer Portal",
        endpoint="app.example.com/search",
    )

    assert build_dedupe_key(first) != build_dedupe_key(second)
