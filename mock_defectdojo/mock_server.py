from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import parse_qs, urlparse


FINDINGS = [
    {
        "id": 12347,
        "title": "SQL Injection",
        "severity": "Critical",
        "description": "SQL injection vulnerability in login endpoint.",
        "impact": "Attackers may read or modify application data.",
        "mitigation": "Use parameterized queries and validate input.",
        "date": "2026-05-27",
        "active": True,
        "verified": True,
        "product": {
            "id": 10,
            "name": "Customer Portal",
        },
        "endpoints": [
            {
                "host": "app.example.com",
                "path": "/login",
            }
        ],
        "ticket_email": "security-ticket@example.com",
    }
]


class MockDefectDojoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/v2/findings/":
            self._send_json({"detail": "Not found"}, status=404)
            return

        query = parse_qs(parsed.query)
        limit = int(query.get("limit", ["100"])[0])
        offset = int(query.get("offset", ["0"])[0])

        active = query.get("active", ["true"])[0].lower() == "true"
        verified = query.get("verified", ["true"])[0].lower() == "true"
        results = [
            finding
            for finding in FINDINGS
            if finding["active"] == active and finding["verified"] == verified
        ]

        page = results[offset : offset + limit]
        payload = {
            "count": len(results),
            "next": None,
            "previous": None,
            "results": page,
        }
        self._send_json(payload)

    def log_message(self, format, *args):
        return

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8080), MockDefectDojoHandler)
    print("Mock DefectDojo listening on http://0.0.0.0:8080", flush=True)
    server.serve_forever()
