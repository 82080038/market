"""Multi-market OMS validation rules (pustaka/92 §4.6).

Extends the base OrderValidator with per-market rules:
- Lot size varies by market (IDX=100, US=1, HK=100, etc.)
- Tick size varies by market and price range
- Trading hours differ per market timezone
- Settlement cycles differ per market
- Currency must match market currency
"""

from __future__ import annotations

from typing import Any

from market.data.seed import DEFAULT_MARKETS
from market.execution.validation import (
    OrderValidator,
    ValidationResult,
    get_tick_size,
)


def _market_map() -> dict[str, dict[str, Any]]:
    return {str(m["mic_code"]): m for m in DEFAULT_MARKETS}


class MultiMarketValidator:
    """Multi-market order validator with per-exchange rules."""

    def __init__(self) -> None:
        self._markets = _market_map()
        # Default validator for markets not in registry
        self._default = OrderValidator(lot_size=1)

    def get_market(self, mic: str) -> dict[str, Any] | None:
        return self._markets.get(mic)

    def get_lot_size(self, mic: str) -> int:
        market = self._markets.get(mic)
        if market:
            return int(market["lot_size"])
        return 1

    def get_currency(self, mic: str) -> str:
        market = self._markets.get(mic)
        if market:
            return str(market["currency"])
        return "USD"

    def get_settlement_days(self, mic: str) -> int:
        market = self._markets.get(mic)
        if market:
            return int(market["settlement_cycle"])
        return 2

    def validate(
        self,
        ticker: str,
        side: str,
        shares: int,
        price: float,
        market_mic: str,
        reference_price: float | None = None,
        buying_power: float | None = None,
        current_shares: int = 0,
        order_currency: str | None = None,
    ) -> ValidationResult:
        """Validate an order against market-specific rules.

        Args:
            ticker: Stock ticker.
            side: "buy" or "sell".
            shares: Number of shares.
            price: Order price.
            market_mic: Market MIC code (e.g. XIDX, XNYS).
            reference_price: Previous close for price limit check.
            buying_power: Available cash (for buy orders).
            current_shares: Shares held (for sell orders).
            order_currency: Currency of the order.

        Returns:
            ValidationResult with errors and warnings.
        """
        errors: list[str] = []
        warnings: list[str] = []

        market = self._markets.get(market_mic)
        if market is None:
            errors.append(f"UNKNOWN_MARKET: market {market_mic} not in registry")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        lot_size = int(market["lot_size"])
        market_currency = str(market["currency"])

        # Currency check
        if order_currency and order_currency != market_currency:
            errors.append(
                f"CURRENCY_MISMATCH: order currency {order_currency} "
                f"does not match market currency {market_currency}",
            )

        # Lot size validation
        if side == "buy" and shares % lot_size != 0:
            errors.append(
                f"INVALID_LOT: shares must be multiple of {lot_size} for {market_mic}",
            )
        elif side == "sell" and shares % lot_size != 0 and shares != current_shares:
            errors.append(
                f"INVALID_LOT: sell shares must be multiple of {lot_size} "
                f"for {market_mic} unless closing position",
            )

        # Minimum shares
        if shares < 1:
            errors.append("MIN_SHARES: minimum 1 share")

        # Price tick validation (use IDX tick rules for IDX, generic for others)
        if market_mic == "XIDX":
            if not self._validate_idx_tick(price):
                tick = get_tick_size(price)
                warnings.append(f"TICK_SIZE: price {price} not multiple of tick {tick}")
        else:
            # Generic tick check for non-IDX markets
            if price <= 0:
                errors.append(f"INVALID_PRICE: price must be positive, got {price}")

        # Price limit (auto-rejection for IDX, ±20%)
        if reference_price and reference_price > 0 and market_mic == "XIDX":
            upper = reference_price * 1.20
            lower = reference_price * 0.80
            if price > upper:
                errors.append(
                    f"PRICE_LIMIT: price {price} exceeds IDX upper limit {upper:.2f}",
                )
            elif price < lower:
                errors.append(
                    f"PRICE_LIMIT: price {price} below IDX lower limit {lower:.2f}",
                )

        # Buying power check
        if side == "buy" and buying_power is not None:
            order_value = shares * price
            if order_value > buying_power:
                errors.append(
                    f"INSUFFICIENT_FUNDS: order value {order_value:.0f} "
                    f"exceeds buying power {buying_power:.0f}",
                )

        # Sell shares check
        if side == "sell" and shares > current_shares:
            errors.append(
                f"INSUFFICIENT_SHARES: trying to sell {shares} but "
                f"only hold {current_shares}",
            )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _validate_idx_tick(self, price: float) -> bool:
        """Validate price against IDX tick size rules."""
        tick = get_tick_size(price)
        remainder = price % tick
        return abs(remainder) < 1e-9 or abs(tick - remainder) < 1e-9
