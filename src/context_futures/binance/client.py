from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class BinanceAPIError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Binance API error {status}: {body}")
        self.status = status
        self.body = body


class BinanceHttpClient:
    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str = "https://fapi.binance.com",
        recv_window: int = 5000,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("BINANCE_FUTURES_KEY")
        self.api_secret = api_secret or os.getenv("BINANCE_FUTURES_SECRET")
        self.base_url = base_url.rstrip("/")
        self.recv_window = recv_window
        self.timeout = timeout

    def public(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request(method, path, params=params, signed=False)

    def signed(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.api_key or not self.api_secret:
            raise ValueError("BINANCE_FUTURES_KEY and BINANCE_FUTURES_SECRET are required")
        params = dict(params or {})
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = self.recv_window
        query = urllib.parse.urlencode(params)
        signature = hmac.new(self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        params["signature"] = signature
        return self._request(method, path, params=params, signed=True)

    def _request(self, method: str, path: str, params: dict[str, Any] | None, signed: bool) -> Any:
        method = method.upper()
        params = _normalize_params(params or {})
        query = urllib.parse.urlencode(params)
        url = f"{self.base_url}{path}"
        data: bytes | None = None
        if method in {"GET", "DELETE"} and query:
            url = f"{url}?{query}"
        elif query:
            data = query.encode("utf-8")

        headers = {"User-Agent": "context-futures/0.1"}
        if signed and self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise BinanceAPIError(exc.code, body) from exc
        if not raw:
            return None
        return json.loads(raw)


def _normalize_params(params: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            normalized[key] = "true" if value else "false"
        else:
            normalized[key] = value
    return normalized
