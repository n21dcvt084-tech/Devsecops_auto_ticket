import json
import logging
from html import escape
from urllib.parse import urljoin

import requests

from config import Settings
from redaction import redact_secrets
from schemas import ManageEngineRequestPayload, ManageEngineRequestResult

logger = logging.getLogger(__name__)

MANAGEENGINE_ACCEPT_HEADER = "application/vnd.manageengine.sdp.v3+json"


def format_manageengine_description(description: str) -> str:
    return escape(description).replace("\n", "<br>")


class ManageEngineClient:
    """Small API wrapper for ServiceDesk Plus v3 request operations."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def create_request(
        self, payload: ManageEngineRequestPayload
    ) -> ManageEngineRequestResult:
        input_data = self._build_input_data(payload)
        if self.settings.manageengine_dry_run:
            logger.info(
                "ManageEngine dry-run create request",
                extra={
                    "finding_id": payload.finding_id,
                    "dedupe_key": payload.dedupe_key,
                    "ticket_action": payload.ticket_action.value,
                },
            )
            return ManageEngineRequestResult(
                request_id=None,
                status="DRY_RUN",
                raw_response={"input_data": input_data},
            )

        response = requests.post(
            self._api_url("api/v3/requests"),
            headers=self._headers(),
            data={"input_data": json.dumps(input_data)},
            timeout=self.settings.manageengine_request_timeout_seconds,
            verify=self.settings.manageengine_verify_ssl,
        )
        response.raise_for_status()
        return self._parse_result(response.json())

    def update_request(
        self, request_id: str, payload: ManageEngineRequestPayload
    ) -> ManageEngineRequestResult:
        input_data = self._build_input_data(payload)
        if self.settings.manageengine_dry_run:
            logger.info(
                "ManageEngine dry-run update request",
                extra={
                    "request_id": request_id,
                    "finding_id": payload.finding_id,
                    "dedupe_key": payload.dedupe_key,
                    "ticket_action": payload.ticket_action.value,
                },
            )
            return ManageEngineRequestResult(
                request_id=request_id,
                status="DRY_RUN",
                raw_response={"input_data": input_data},
            )

        response = requests.put(
            self._api_url(f"api/v3/requests/{request_id}"),
            headers=self._headers(),
            data={"input_data": json.dumps(input_data)},
            timeout=self.settings.manageengine_request_timeout_seconds,
            verify=self.settings.manageengine_verify_ssl,
        )
        response.raise_for_status()
        return self._parse_result(response.json())

    def add_note(self, request_id: str, note: str) -> ManageEngineRequestResult:
        input_data = {"note": {"description": redact_secrets(note)}}
        if self.settings.manageengine_dry_run:
            logger.info(
                "ManageEngine dry-run add note",
                extra={"request_id": request_id},
            )
            return ManageEngineRequestResult(
                request_id=request_id,
                status="DRY_RUN",
                raw_response={"input_data": input_data},
            )

        response = requests.post(
            self._api_url(f"api/v3/requests/{request_id}/notes"),
            headers=self._headers(),
            data={"input_data": json.dumps(input_data)},
            timeout=self.settings.manageengine_request_timeout_seconds,
            verify=self.settings.manageengine_verify_ssl,
        )
        response.raise_for_status()
        return self._parse_result(response.json(), fallback_request_id=request_id)

    def _build_input_data(self, payload: ManageEngineRequestPayload) -> dict:
        request = {
            "subject": redact_secrets(payload.subject),
            "description": format_manageengine_description(redact_secrets(payload.description)),
            "status": {"name": payload.status},
        }
        if payload.requester_name or payload.requester_email:
            requester = {}
            if payload.requester_name:
                requester["name"] = payload.requester_name
            if payload.requester_email:
                requester["email_id"] = str(payload.requester_email)
            request["requester"] = requester
        if payload.priority:
            request["priority"] = {"name": payload.priority}
        if payload.group:
            request["group"] = {"name": payload.group}
        if payload.category:
            request["category"] = {"name": payload.category}
        if payload.subcategory:
            request["subcategory"] = {"name": payload.subcategory}
        if payload.impact_details:
            request["impact_details"] = redact_secrets(payload.impact_details)

        return {"request": request}

    def _headers(self) -> dict[str, str]:
        if not self.settings.manageengine_auth_token:
            raise ValueError("MANAGEENGINE_AUTH_TOKEN is required when dry-run is disabled")
        return {
            "Accept": MANAGEENGINE_ACCEPT_HEADER,
            "Content-Type": "application/x-www-form-urlencoded",
            "authtoken": self.settings.manageengine_auth_token,
        }

    def _api_url(self, path: str) -> str:
        if not self.settings.manageengine_base_url:
            raise ValueError("MANAGEENGINE_BASE_URL is required")
        return urljoin(self.settings.manageengine_base_url + "/", path.lstrip("/"))

    def _parse_result(
        self, raw_response: dict, fallback_request_id: str | None = None
    ) -> ManageEngineRequestResult:
        request = raw_response.get("request") or {}
        response_status = raw_response.get("response_status") or {}
        request_id = request.get("id") or fallback_request_id
        status = response_status.get("status") or "UNKNOWN"
        return ManageEngineRequestResult(
            request_id=str(request_id) if request_id else None,
            status=str(status),
            raw_response=raw_response,
        )
