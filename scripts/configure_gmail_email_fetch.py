import json
from getpass import getpass
from pathlib import Path


ENV_PATH = Path(".env")


def read_env(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(".env does not exist")
    return path.read_text(encoding="utf-8").splitlines()


def update_env(lines: list[str], updates: dict[str, str]) -> list[str]:
    seen: set[str] = set()
    updated_lines: list[str] = []

    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            updated_lines.append(line)
            continue

        key = line.split("=", 1)[0]
        if key in updates:
            updated_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            updated_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            updated_lines.append(f"{key}={value}")

    return updated_lines


def normalize_app_password(value: str) -> str:
    return value.replace(" ", "").strip()


def main() -> int:
    backend_address = input("Backend Gmail address: ").strip()
    backend_app_password = normalize_app_password(getpass("Backend Gmail App Password: "))
    from_name = input("Backend From name: ").strip() or "DevSecOps Automation"
    incoming_address = input("ManageEngine Incoming Gmail address: ").strip()
    incoming_app_password = normalize_app_password(
        getpass("ManageEngine Incoming Gmail App Password: ")
    )
    product_name = (
        input("DefectDojo product name [demo-devsecops-project]: ").strip()
        or "demo-devsecops-project"
    )
    findings_limit = input("Test findings limit [1]: ").strip() or "1"

    mapping = {
        "projects": [
            {
                "project_name": product_name,
                "product_name": product_name,
                "email_destinations": [incoming_address],
            }
        ]
    }

    updates = {
        "DEFECTDOJO_FINDINGS_LIMIT": findings_limit,
        "PROJECT_EMAIL_MAPPING_FILE": "",
        "PROJECT_EMAIL_MAPPING_JSON": json.dumps(mapping, separators=(",", ":")),
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SMTP_USERNAME": backend_address,
        "SMTP_PASSWORD": backend_app_password,
        "SMTP_FROM_EMAIL": f"{from_name} <{backend_address}>",
        "SMTP_USE_TLS": "true",
        "IMAP_HOST": "imap.gmail.com",
        "IMAP_SSL_PORT": "993",
        "IMAP_USERNAME": incoming_address,
        "IMAP_PASSWORD": incoming_app_password,
        "MANAGEENGINE_DELIVERY_MODE": "email_fetch",
        "MANAGEENGINE_ENABLED": "false",
        "MANAGEENGINE_DRY_RUN": "true",
    }

    updated_lines = update_env(read_env(ENV_PATH), updates)
    ENV_PATH.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

    print("Configured .env for Gmail email_fetch test.")
    print(f"Backend Gmail: {backend_address}")
    print(f"ManageEngine Incoming Gmail: {incoming_address}")
    print(f"DefectDojo Product: {product_name}")
    print(f"Test Findings Limit: {findings_limit}")
    print("Secrets were written only to local .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
