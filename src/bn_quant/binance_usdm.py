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


class BinanceFuturesClient:
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

    def server_time(self) -> dict[str, Any]:
        return self.public("GET", "/fapi/v1/time")

    def exchange_info(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"symbol": symbol} if symbol else None
        return self.public("GET", "/fapi/v1/exchangeInfo", params=params)

    def klines(
        self,
        symbol: str,
        interval: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1500,
    ) -> list[list[Any]]:
        params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        return self.public("GET", "/fapi/v1/klines", params=params)

    def premium_index(self, symbol: str) -> dict[str, Any]:
        return self.public("GET", "/fapi/v1/premiumIndex", params={"symbol": symbol})

    def open_interest(self, symbol: str) -> dict[str, Any]:
        return self.public("GET", "/fapi/v1/openInterest", params={"symbol": symbol})

    def open_interest_statistics(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 2,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"symbol": symbol, "period": period, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        return self.public("GET", "/futures/data/openInterestHist", params=params)

    def taker_buy_sell_volume(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 1,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"symbol": symbol, "period": period, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        return self.public("GET", "/futures/data/takerlongshortRatio", params=params)

    def funding_rate_history(
        self,
        symbol: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"symbol": symbol, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        return self.public("GET", "/fapi/v1/fundingRate", params=params)

    def account(self) -> dict[str, Any]:
        return self.signed("GET", "/fapi/v2/account")

    def position_risk(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        return self.signed("GET", "/fapi/v2/positionRisk", params=params)

    def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        return self.signed("POST", "/fapi/v1/leverage", params={"symbol": symbol, "leverage": leverage})

    def set_margin_type(self, symbol: str, margin_type: str) -> dict[str, Any]:
        return self.signed("POST", "/fapi/v1/marginType", params={"symbol": symbol, "marginType": margin_type.upper()})

    def new_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str | None = None,
        price: str | None = None,
        stop_price: str | None = None,
        reduce_only: bool | None = None,
        time_in_force: str | None = None,
        new_client_order_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
        }
        if quantity is not None:
            params["quantity"] = quantity
        if price is not None:
            params["price"] = price
        if stop_price is not None:
            params["stopPrice"] = stop_price
        if reduce_only is not None:
            params["reduceOnly"] = "true" if reduce_only else "false"
        if time_in_force is not None:
            params["timeInForce"] = time_in_force
        if new_client_order_id is not None:
            params["newClientOrderId"] = new_client_order_id
        if extra:
            params.update(extra)
        return self.signed("POST", "/fapi/v1/order", params=params)

    def cancel_order(
        self,
        symbol: str,
        order_id: int | None = None,
        orig_client_order_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"symbol": symbol}
        if order_id is not None:
            params["orderId"] = order_id
        if orig_client_order_id is not None:
            params["origClientOrderId"] = orig_client_order_id
        return self.signed("DELETE", "/fapi/v1/order", params=params)

    def query_order(
        self,
        symbol: str,
        order_id: int | None = None,
        orig_client_order_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"symbol": symbol}
        if order_id is not None:
            params["orderId"] = order_id
        if orig_client_order_id is not None:
            params["origClientOrderId"] = orig_client_order_id
        return self.signed("GET", "/fapi/v1/order", params=params)

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

        headers = {"User-Agent": "bn-quant-starter/0.1"}
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
