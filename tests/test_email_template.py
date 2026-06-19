import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from email_template import build_body, build_html_body, build_subject, build_ticket_content
from schemas import DefectDojoFinding

FIXED_GENERATED_AT = datetime(2026, 6, 15, 8, 30, 45, tzinfo=timezone.utc)


def test_email_subject_matches_researched_format():
    finding = DefectDojoFinding(
        finding_id=3282,
        title="SQL Injection",
        severity="Critical",
        product="Customer Portal",
    )

    assert build_subject(finding) == (
        "[VJA-DEVSECOPS] [Critical] [Customer Portal] - "
        "FindingID: 3282 - SQL Injection"
    )


def test_email_body_contains_ticket_parse_fields():
    finding = DefectDojoFinding(
        finding_id=3282,
        title="SQL Injection",
        severity="Critical",
        product="Customer Portal",
        endpoint="app.example.com/login",
    )

    body = build_body(
        finding,
        "https://dojo.example.com",
        manageengine_public_url="https://servicedesk.example.com",
        generated_at=FIXED_GENERATED_AT,
    )

    assert "You are receiving this email because DefectDojo detected" in body
    assert "DefectDojo URL:" in body
    assert "Finding Details" in body
    assert "- Project: Customer Portal" in body
    assert "- Severity: Critical" in body
    assert "- Endpoint: app.example.com/login" in body
    assert "- Component:" not in body
    assert "- CWE:" not in body
    assert "- CVE:" not in body
    assert "- File Path:" not in body
    assert "- Finding ID: 3282" not in body
    assert "- Finding Title: SQL Injection" not in body
    assert "- Finding Date:" not in body
    assert "Ticket Routing Fields" not in body
    assert "- Group: N/A" not in body
    assert "- Category: N/A" not in body
    assert "- Subcategory: N/A" not in body
    assert "Recommended Actions" not in body
    assert "Review the finding details in DefectDojo" not in body
    assert "https://dojo.example.com/finding/3282" in body
    assert "ManageEngine Ticket URL: https://servicedesk.example.com/WOListView.do" in body
    assert "For support, contact DevSecOps Team." in body


def test_email_subject_is_truncated_to_200_characters():
    finding = DefectDojoFinding(
        finding_id=3282,
        title="Very long vulnerability title " * 20,
        severity="Critical",
        product="Customer Portal",
    )

    subject = build_subject(finding)

    assert len(subject) == 200
    assert subject.endswith(".....")


def test_cloud_email_subject_redacts_aws_account_id():
    finding = DefectDojoFinding(
        finding_id=6055,
        title=(
            "ELBv2.1 Application Load Balancer Should Be Configured to Redirect "
            "All HTTP Requests to HTTPS - Resource: 012345678912"
        ),
        severity="Info",
        product="demo-dojo",
        scanner_type="AWS Security Hub Scan",
    )

    subject = build_subject(finding)

    assert "Resource: XXXXXX" in subject
    assert "012345678912" not in subject


def test_cloud_email_subject_summarizes_securityhub_arn():
    finding = DefectDojoFinding(
        finding_id=6056,
        title=(
            "Control ID: arn:aws:securityhub:us-east-1:012345678912:"
            "subscription/aws-foundational-security-best-practices/v/1.0.0/"
            "ELBv2.1/finding/27aa50f4-d793-4e54-8649-4522e876230f"
        ),
        severity="Info",
        product="demo-dojo",
        scanner_type="AWS Security Hub Scan",
    )

    subject = build_subject(finding)

    assert "Control ID: ELBv2.1" in subject
    assert "Finding Reference: 27aa50f4...230f" in subject
    assert "012345678912" not in subject
    assert "27aa50f4-d793-4e54-8649-4522e876230f" not in subject


def test_html_email_body_contains_clickable_defectdojo_link():
    finding = DefectDojoFinding(
        finding_id=3282,
        title="SQL Injection",
        severity="Critical",
        product="Customer Portal",
        endpoint="app.example.com/login",
    )

    html_body = build_html_body(
        finding,
        "https://dojo.example.com",
        manageengine_public_url="https://servicedesk.example.com",
        generated_at=FIXED_GENERATED_AT,
    )

    assert '<a href="https://dojo.example.com/finding/3282">' in html_body
    assert "Open DefectDojo Finding 3282" in html_body
    assert '<a href="https://servicedesk.example.com/WOListView.do">' in html_body
    assert "Open ManageEngine Requests" in html_body
    assert "<p>Finding Details</p>" in html_body
    assert "<li>Project: Customer Portal</li>" in html_body
    assert "<li>Severity: Critical</li>" in html_body
    assert "<li>Endpoint: app.example.com/login</li>" in html_body
    assert "<li>Component:" not in html_body
    assert "<li>CWE:" not in html_body
    assert "<li>CVE:" not in html_body
    assert "<li>File Path:" not in html_body
    assert "<li>Finding ID: 3282</li>" not in html_body
    assert "<li>Finding Date:" not in html_body
    assert "<strong>" not in html_body
    assert "<h3>" not in html_body
    assert "Ticket Routing Fields" not in html_body
    assert "Recommended Actions" not in html_body
    assert "Review the finding details in DefectDojo" not in html_body
    assert "For support, contact DevSecOps Team." in html_body


def test_email_body_omits_manageengine_routing_fields_until_enabled():
    finding = DefectDojoFinding(
        finding_id=3282,
        title="SQL Injection",
        severity="Critical",
        product="Customer Portal",
    )

    body = build_body(
        finding,
        "https://dojo.example.com",
        group="DevSecOps",
        category="Security",
        subcategory="Vulnerability",
        generated_at=FIXED_GENERATED_AT,
    )

    assert "Ticket Routing Fields" not in body
    assert "- Group: DevSecOps" not in body
    assert "- Category: Security" not in body
    assert "- Subcategory: Vulnerability" not in body


def test_dependency_template_uses_component_cve_cwe_and_file_path():
    finding = DefectDojoFinding(
        finding_id=6051,
        title="CVE-2021-3744 - Linux",
        severity="Medium",
        product="demo-dojo",
        component_name="linux",
        component_version="5.4",
        cve="CVE-2021-3744",
        cwe=79,
        file_path="package-lock.json",
    )

    body = build_body(
        finding,
        "https://dojo.example.com",
        generated_at=FIXED_GENERATED_AT,
    )

    assert "- Project: demo-dojo" in body
    assert "- Severity: Medium" in body
    assert "- Component: linux:5.4" in body
    assert "- CWE: 79" in body
    assert "- CVE: CVE-2021-3744" in body
    assert "- File Path: package-lock.json" in body
    assert "- Endpoint:" not in body


def test_cloud_template_uses_resource_fields_and_omits_empty_cve_fields():
    finding = DefectDojoFinding(
        finding_id=6052,
        title="AWS Security Hub control failed",
        severity="Medium",
        product="demo-dojo",
        scanner_type="AWS Security Hub Scan",
        component_name="AwsAccount",
        cve="[]",
        impact=(
            "Resource: 012345678912\n"
            "Region: ap-southeast-1\n"
            "Compliance Status: FAILED"
        ),
        rule_id="AWS.SecurityHub.Control.1",
    )

    body = build_body(
        finding,
        "https://dojo.example.com",
        generated_at=FIXED_GENERATED_AT,
    )
    html_body = build_html_body(
        finding,
        "https://dojo.example.com",
        generated_at=FIXED_GENERATED_AT,
    )

    assert "- Project: demo-dojo" in body
    assert "- Severity: Medium" in body
    assert "- Resource: XXXXXX" in body
    assert "- Resource Type: AwsAccount" in body
    assert "- Region: ap-southeast-1" in body
    assert "- Control ID: AWS.SecurityHub.Control.1" in body
    assert "- Compliance Status: FAILED" in body
    assert "012345678912" not in body
    assert "- CVE:" not in body
    assert "- CWE:" not in body
    assert "- File Path:" not in body
    assert "<li>Resource: XXXXXX</li>" in html_body
    assert "<li>CVE:" not in html_body


def test_cloud_template_summarizes_securityhub_arn_without_exposing_account():
    finding = DefectDojoFinding(
        finding_id=6053,
        title="ELBv2.1 load balancer control failed",
        severity="Medium",
        product="demo-dojo",
        scanner_type="AWS Security Hub Scan",
        component_name="AwsAccount",
        rule_id=(
            "arn:aws:securityhub:us-east-1:012345678912:"
            "subscription/aws-foundational-security-best-practices/v/1.0.0/"
            "ELBv2.1/finding/27aa50f4-d793-4e54-8649-4522e876230f"
        ),
        impact="Resource: arn:aws:elasticloadbalancing:us-east-1:012345678912:loadbalancer/app/demo/abc123",
    )

    body = build_body(
        finding,
        "https://dojo.example.com",
        generated_at=FIXED_GENERATED_AT,
    )

    assert "- Control ID: ELBv2.1" in body
    assert "- Standard: AWS Foundational Security Best Practices v1.0.0" in body
    assert "- AWS Account: XXXXXX" in body
    assert "- Region: us-east-1" in body
    assert "- Finding Reference: 27aa50f4...230f" in body
    assert "012345678912" not in body
    assert "27aa50f4-d793-4e54-8649-4522e876230f" not in body


def test_sast_template_uses_file_rule_line_and_cwe():
    finding = DefectDojoFinding(
        finding_id=7001,
        title="Hardcoded secret",
        severity="High",
        product="api-service",
        scanner_type="Semgrep",
        file_path="src/settings.py",
        line=42,
        rule_id="python.lang.security.audit.hardcoded-secret",
        cwe=798,
    )

    body = build_body(
        finding,
        "https://dojo.example.com",
        generated_at=FIXED_GENERATED_AT,
    )

    assert "- File Path: src/settings.py" in body
    assert "- Line: 42" in body
    assert "- Rule ID: python.lang.security.audit.hardcoded-secret" in body
    assert "- CWE: 798" in body
    assert "- CVE:" not in body
    assert "- Endpoint:" not in body


def test_dast_template_uses_endpoint_parameter_rule_and_cwe():
    finding = DefectDojoFinding(
        finding_id=8001,
        title="Reflected XSS",
        severity="High",
        product="web-portal",
        scanner_type="ZAP Scan",
        endpoint="https://app.example.com/search",
        parameter="q",
        rule_id="zap-xss",
        cwe=79,
    )

    body = build_body(
        finding,
        "https://dojo.example.com",
        generated_at=FIXED_GENERATED_AT,
    )

    assert "- Endpoint: https://app.example.com/search" in body
    assert "- Parameter: q" in body
    assert "- Rule ID: zap-xss" in body
    assert "- CWE: 79" in body
    assert "- CVE:" not in body
    assert "- File Path:" not in body


def test_email_body_strips_markdown_bold_markers_from_paragraphs():
    finding = DefectDojoFinding(
        finding_id=3282,
        title="Dependency CVE",
        severity="High",
        product="Customer Portal",
        impact=(
            "Package is vulnerable.\n"
            "**Source:** OSSINDEX\n"
            "**Filepath:** /codebuild_docker_build/nodejs-demoapp/src/package-lock.json?cross-spawn"
        ),
    )

    body = build_body(
        finding,
        "https://dojo.example.com",
        generated_at=FIXED_GENERATED_AT,
    )
    html_body = build_html_body(
        finding,
        "https://dojo.example.com",
        generated_at=FIXED_GENERATED_AT,
    )

    assert "**Source:**" not in body
    assert "**Filepath:**" not in body
    assert "Source: OSSINDEX" in body
    assert "Filepath: /codebuild_docker_build/nodejs-demoapp/src/package-lock.json?cross-spawn" in body
    assert "**Source:**" not in html_body
    assert "**Filepath:**" not in html_body
    assert "<p>Source: OSSINDEX</p>" in html_body
    assert (
        "<p>Filepath: /codebuild_docker_build/nodejs-demoapp/src/package-lock.json?cross-spawn</p>"
        in html_body
    )



def test_email_template_redacts_secret_values():
    finding = DefectDojoFinding(
        finding_id=3282,
        title="Leaked API Key api_key=abc123456789SECRET",
        severity="Critical",
        product="Customer Portal",
        description="Authorization: Token ffffffffffffffffffffffffffffffffffffffff",
        impact="password=SuperSecret123 may be exposed",
        mitigation="Rotate secret_key='secret-value-12345' immediately",
    )

    subject = build_subject(finding)
    body = build_body(
        finding,
        "https://dojo.example.com",
        generated_at=FIXED_GENERATED_AT,
    )

    assert "abc123456789SECRET" not in subject
    assert "ffffffffffffffffffffffffffffffffffffffff" not in body
    assert "SuperSecret123" not in body
    assert "secret-value-12345" not in body
    assert "XXXXXX" in subject
    assert "XXXXXX" in body


def test_ticket_content_wraps_email_subject_and_body():
    finding = DefectDojoFinding(
        finding_id=3282,
        title="SQL Injection",
        severity="Critical",
        product="Customer Portal",
        endpoint="app.example.com/login",
    )

    content = build_ticket_content(
        finding,
        "https://dojo.example.com",
        dedupe_key="dd:test",
        group="DevSecOps",
        category="Security",
        subcategory="Vulnerability",
        generated_at=FIXED_GENERATED_AT,
    )

    assert content.subject == build_subject(finding)
    assert content.body == build_body(
        finding,
        "https://dojo.example.com",
        dedupe_key="dd:test",
        group="DevSecOps",
        category="Security",
        subcategory="Vulnerability",
        generated_at=FIXED_GENERATED_AT,
    )
    assert content.html_body == build_html_body(
        finding,
        "https://dojo.example.com",
        dedupe_key="dd:test",
        group="DevSecOps",
        category="Security",
        subcategory="Vulnerability",
        generated_at=FIXED_GENERATED_AT,
    )
    assert content.finding_id == 3282
    assert content.dedupe_key == "dd:test"
    assert content.priority == "N/A"
    assert content.sla_target == "N/A"
    assert content.group == "DevSecOps"
    assert content.category == "Security"
    assert content.subcategory == "Vulnerability"
