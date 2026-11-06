"""Legacy synchronous HTTP client; the frontend talks only to FastAPI."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ApiError(RuntimeError):
    """A backend request failed or returned an invalid response."""


class IncidentMindApi:
    def __init__(self, base_url: str | None = None, *, timeout: float = 8.0) -> None:
        self.base_url = (base_url or os.getenv("INCIDENTMIND_API_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.timeout = timeout

    def list_incidents(self, *, limit: int = 50) -> list[dict]:
        return self._request("GET", f"/incidents?limit={limit}")

    def get_incident(self, incident_id: str) -> dict:
        return self._request("GET", f"/incidents/{incident_id}")

    def analyze(self, incident_id: str, *, innovation_enabled: bool = True) -> dict:
        flag = "true" if innovation_enabled else "false"
        return self._request("POST", f"/incidents/{incident_id}/analyze?innovation_enabled={flag}")

    def submit_feedback(self, incident_id: str, payload: dict) -> dict:
        return self._request("POST", f"/incidents/{incident_id}/feedback", payload)

    def replay(self, incident_ids: list[str]) -> dict:
        return self._request("POST", "/innovation/replay", {"incident_ids": incident_ids})

    def outcome_stats(self) -> dict:
        return self._request("GET", "/stats/outcomes")

    def memory_stats(self) -> dict:
        return self._request("GET", "/stats/memory")

    def memory_origin_stats(self) -> dict:
        return self._request("GET", "/stats/memory/origins")

    def _request(self, method: str, path: str, payload: dict | None = None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"} if body is not None else {},
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("detail", "Backend request failed")
            except (ValueError, AttributeError):
                detail = "Backend request failed"
            raise ApiError(f"HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ApiError(f"Cannot reach IncidentMind API at {self.base_url}: {exc}") from exc
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise ApiError("IncidentMind API returned invalid JSON") from exc
