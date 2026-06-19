import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import Settings
from defectdojo_client import DefectDojoClient


def build_settings(**overrides):
    values = {
        "DEFECTDOJO_BASE_URL": "https://dojo.example.com",
        "DEFECTDOJO_API_TOKEN": "token",
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
        "SMTP_HOST": "localhost",
        "SMTP_FROM_EMAIL": "devsecops@example.com",
        **overrides,
    }
    return Settings.model_validate(values)


def test_maps_vulnerability_id_dict_to_plain_cve_value():
    client = DefectDojoClient(build_settings())

    finding = client._map_finding(
        {
            "id": 3172,
            "title": "cross-spawn:7.0.3 | CVE-2024-21538",
            "severity": "High",
            "product": {"name": "demo-devsecops-project"},
            "vulnerability_ids": [{"vulnerability_id": "CVE-2024-21538"}],
        }
    )

    assert finding.cve == "CVE-2024-21538"
