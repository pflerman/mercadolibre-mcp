"""HTTP client for MercadoLibre API with automatic auth."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from ml_auth import MLAuth

BASE_URL = "https://api.mercadolibre.com"


class MLClient:
    """Thin wrapper around httpx with Bearer auth and auto-refresh."""

    def __init__(self, auth: MLAuth, reader_auth: MLAuth | None = None):
        self.auth = auth
        self.reader_auth = reader_auth
        self._http = httpx.Client(base_url=BASE_URL, timeout=30)

    @property
    def user_id(self) -> int:
        return self.auth.user_id

    def _headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get(self, path: str, params: dict | None = None) -> Any:
        resp = self._http.get(path, headers=self._headers(self.auth.access_token), params=params)
        if resp.status_code == 403 and self.reader_auth:
            resp = self._http.get(path, headers=self._headers(self.reader_auth.access_token), params=params)
        if resp.status_code == 401:
            self.auth._refresh()
            resp = self._http.get(path, headers=self._headers(self.auth.access_token), params=params)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, json_data: Any = None) -> Any:
        resp = self._http.post(path, headers=self._headers(self.auth.access_token), json=json_data)
        if resp.status_code == 401:
            self.auth._refresh()
            resp = self._http.post(path, headers=self._headers(self.auth.access_token), json=json_data)
        resp.raise_for_status()
        return resp.json()

    def put(self, path: str, json_data: Any = None) -> Any:
        resp = self._http.put(path, headers=self._headers(self.auth.access_token), json=json_data)
        if resp.status_code == 401:
            self.auth._refresh()
            resp = self._http.put(path, headers=self._headers(self.auth.access_token), json=json_data)
        resp.raise_for_status()
        return resp.json()

    def delete(self, path: str) -> Any:
        resp = self._http.delete(path, headers=self._headers(self.auth.access_token))
        if resp.status_code == 401:
            self.auth._refresh()
            resp = self._http.delete(path, headers=self._headers(self.auth.access_token))
        resp.raise_for_status()
        if resp.status_code == 204:
            return {"status": "ok"}
        return resp.json()

    def upload(self, file_path: str) -> Any:
        """Upload image via multipart/form-data."""
        p = Path(file_path)
        with open(p, "rb") as f:
            resp = self._http.post(
                "/pictures/items/upload",
                headers={"Authorization": f"Bearer {self.auth.access_token}"},
                files={"file": (p.name, f, "image/jpeg")},
            )
        if resp.status_code == 401:
            self.auth._refresh()
            with open(p, "rb") as f:
                resp = self._http.post(
                    "/pictures/items/upload",
                    headers={"Authorization": f"Bearer {self.auth.access_token}"},
                    files={"file": (p.name, f, "image/jpeg")},
                )
        resp.raise_for_status()
        return resp.json()
