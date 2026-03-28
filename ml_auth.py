"""Token management for MercadoLibre API."""

import json
import time
from pathlib import Path

import httpx


class MLAuth:
    """Handles ML OAuth token lifecycle: load, check expiry, refresh, save."""

    TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
    EXPIRY_BUFFER = 300  # refresh 5 min before expiry

    def __init__(self, credentials_path: str):
        self.credentials_path = Path(credentials_path)
        self.credentials: dict = {}
        self._load()

    def _load(self):
        if self.credentials_path.exists():
            self.credentials = json.loads(self.credentials_path.read_text())

    def _save(self):
        self.credentials_path.write_text(
            json.dumps(self.credentials, indent=2, ensure_ascii=False)
        )

    @property
    def access_token(self) -> str:
        self._ensure_valid()
        return self.credentials["access_token"]

    @property
    def user_id(self) -> int:
        return self.credentials.get("user_id", 0)

    def _is_expired(self) -> bool:
        ts = self.credentials.get("timestamp", 0)
        expires = self.credentials.get("expires_in", 21600)
        return time.time() - ts >= (expires - self.EXPIRY_BUFFER)

    def _ensure_valid(self):
        if self._is_expired():
            self._refresh()

    def _refresh(self):
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.credentials["app_id"],
            "client_secret": self.credentials["client_secret"],
            "refresh_token": self.credentials["refresh_token"],
        }
        resp = httpx.post(self.TOKEN_URL, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        self.credentials["access_token"] = data["access_token"]
        self.credentials["refresh_token"] = data["refresh_token"]
        self.credentials["expires_in"] = data.get("expires_in", 21600)
        self.credentials["timestamp"] = time.time()
        if "user_id" in data:
            self.credentials["user_id"] = data["user_id"]
        self._save()
