import os
import requests


class ApiClient:
    def __init__(self, base_url: str):
        base = (base_url or "").strip()
        if not base:
            base = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
        self.base_url = base.rstrip("/")
        self.session = requests.Session()

    def get(self, path: str):
        return self._request("GET", path)

    def post(self, path: str, json_body: dict | None = None):
        return self._request("POST", path, json=json_body)

    def patch(self, path: str, json_body: dict | None = None):
        return self._request("PATCH", path, json=json_body)

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.request(method, url, timeout=120, **kwargs)
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc), "status": None}

        try:
            data = resp.json()
        except ValueError:
            data = resp.text

        if not resp.ok:
            return {
                "ok": False,
                "error": data if isinstance(data, str) else str(data),
                "status": resp.status_code,
            }

        return {"ok": True, "data": data, "status": resp.status_code}
