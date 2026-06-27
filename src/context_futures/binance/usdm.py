from __future__ import annotations

from typing import Any

from .client import BinanceHttpClient


class BinanceUsdmClient:
    def __init__(
        self,
        http: BinanceHttpClient | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str = "https://fapi.binance.com",
        recv_window: int = 5000,
        timeout: float = 10.0,
    ) -> None:
        self.http = http or BinanceHttpClient(
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url,
            recv_window=recv_window,
            timeout=timeout,
        )

    def server_time(self) -> dict[str, Any]:
        return self.http.public("GET", "/fapi/v1/time")

    def exchange_info(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"symbol": symbol} if symbol else None
        return self.http.public("GET", "/fapi/v1/exchangeInfo", params=params)

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
        return self.http.public("GET", "/fapi/v1/klines", params=params)

    def premium_index(self, symbol: str) -> dict[str, Any]:
        return self.http.public("GET", "/fapi/v1/premiumIndex", params={"symbol": symbol})

    def open_interest(self, symbol: str) -> dict[str, Any]:
        return self.http.public("GET", "/fapi/v1/openInterest", params={"symbol": symbol})

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
        return self.http.public("GET", "/futures/data/openInterestHist", params=params)

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
        return self.http.public("GET", "/futures/data/takerlongshortRatio", params=params)

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
        return self.http.public("GET", "/fapi/v1/fundingRate", params=params)

    def account(self) -> dict[str, Any]:
        return self.http.signed("GET", "/fapi/v2/account")

    def position_risk(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        return self.http.signed("GET", "/fapi/v2/positionRisk", params=params)

    def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        return self.http.signed("POST", "/fapi/v1/leverage", params={"symbol": symbol, "leverage": leverage})

    def set_margin_type(self, symbol: str, margin_type: str) -> dict[str, Any]:
        return self.http.signed(
            "POST",
            "/fapi/v1/marginType",
            params={"symbol": symbol, "marginType": margin_type.upper()},
        )

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
        return self.http.signed("POST", "/fapi/v1/order", params=params)

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
        return self.http.signed("DELETE", "/fapi/v1/order", params=params)

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
        return self.http.signed("GET", "/fapi/v1/order", params=params)
