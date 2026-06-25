import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import Response

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from health import health_check


class SchedulerState:
    def __init__(self, running: bool):
        self.running = running

    def is_running(self):
        return self.running


def build_request(running: bool):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(scheduler=SchedulerState(running))
        )
    )


def test_health_returns_503_when_database_is_disconnected(monkeypatch):
    monkeypatch.setattr("health.check_database_connection", lambda: False)

    response = Response()
    body = health_check(build_request(running=True), response)

    assert response.status_code == 503
    assert body["status"] == "error"
    assert body["database"] == "disconnected"


def test_health_returns_503_when_scheduler_is_stopped(monkeypatch):
    monkeypatch.setattr("health.check_database_connection", lambda: True)

    response = Response()
    body = health_check(build_request(running=False), response)

    assert response.status_code == 503
    assert body["scheduler"] == "stopped"
