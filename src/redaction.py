import re

MASK = "XXXXXX"

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b("
    r"api[_\s-]*key|secret[_\s-]*key|access[_\s-]*token|auth[_\s-]*token|"
    r"client[_\s-]*secret|refresh[_\s-]*token|password|passwd|pwd"
    r")\b\s*([:=])\s*([\"']?)([^\s\"';&<>]{4,})([\"']?)"
)

_AUTH_HEADER = re.compile(
    r"(?i)\b(Authorization\s*:\s*(?:Token|Bearer|Basic))\s+([^\s]+)"
)

_AWS_ACCESS_KEY = re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")
_GITHUB_TOKEN = re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")
_LONG_HEX_SECRET = re.compile(r"\b[a-fA-F0-9]{32,}\b")


def redact_secrets(value: object) -> str:
    """Mask likely secrets before content is sent by email or stored in templates."""
    if value is None:
        return "N/A"

    text = str(value)
    text = _AUTH_HEADER.sub(r"\1 " + MASK, text)
    text = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}{MASK}{match.group(5)}", text)
    text = _AWS_ACCESS_KEY.sub(MASK, text)
    text = _GITHUB_TOKEN.sub(MASK, text)
    text = _LONG_HEX_SECRET.sub(MASK, text)
    return text
