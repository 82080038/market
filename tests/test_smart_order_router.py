"""Tests for Smart Order Router (Gap #7)."""

from __future__ import annotations

import pytest

from market.execution.smart_order_router import (
    OrderSide,
    RoutingConfig,
    RoutingDecision,
    RoutingStrategy,
    SmartOrderRouter,
    VenueQuote,
)


@pytest.fixture
def router() -> SmartOrderRouter:
    return SmartOrderRouter()


@pytest.fixture
def router_with_venues(router: SmartOrderRouter) -> SmartOrderRouter:
    """Router with multiple venue quotes."""
    router.update_venue_quote(VenueQuote(
        venue="broker_a", bid=89900, ask=90000,
        bid_size=5000, ask_size=5000,
        commission_rate=0.0015, latency_ms=50, reliability=0.99,
    ))
    router.update_venue_quote(VenueQuote(
        venue="broker_b", bid=89850, ask=89950,
        bid_size=3000, ask_size=3000,
        commission_rate=0.0010, latency_ms=100, reliability=0.98,
    ))
    router.update_venue_quote(VenueQuote(
        venue="broker_c", bid=90050, ask=90100,
        bid_size=10000, ask_size=10000,
        commission_rate=0.0020, latency_ms=200, reliability=0.95,
    ))
    return router


def test_routing_strategy_enum():
    """RoutingStrategy has expected values."""
    assert RoutingStrategy.BEST_PRICE.value == "best_price"
    assert RoutingStrategy.BEST_EXECUTION.value == "best_execution"
    assert RoutingStrategy.TWAP.value == "twap"
    assert RoutingStrategy.VWAP.value == "vwap"


def test_route_no_venues(router: SmartOrderRouter):
    """route returns None when no venues are registered."""
    result = router.route("ORD-1", "BBCA.JK", OrderSide.BUY, 100)
    assert result is None


def test_route_best_price_buy(router_with_venues: SmartOrderRouter):
    """BEST_PRICE routes to lowest ask for buy."""
    router_with_venues.config.strategy = RoutingStrategy.BEST_PRICE
    result = router_with_venues.route("ORD-1", "BBCA.JK", OrderSide.BUY, 100)
    assert result is not None
    assert result.venue == "broker_b"  # Lowest ask
    assert result.expected_price == 89950


def test_route_best_price_sell(router_with_venues: SmartOrderRouter):
    """BEST_PRICE routes to highest bid for sell."""
    router_with_venues.config.strategy = RoutingStrategy.BEST_PRICE
    result = router_with_venues.route("ORD-1", "BBCA.JK", OrderSide.SELL, 100)
    assert result is not None
    assert result.venue == "broker_c"  # Highest bid
    assert result.expected_price == 90050


def test_route_least_cost(router_with_venues: SmartOrderRouter):
    """LEAST_COST routes to lowest total cost."""
    router_with_venues.config.strategy = RoutingStrategy.LEAST_COST
    result = router_with_venues.route("ORD-1", "BBCA.JK", OrderSide.BUY, 100)
    assert result is not None
    assert result.strategy == RoutingStrategy.LEAST_COST
    # Should consider price + commission + slippage
    assert result.expected_cost > 0


def test_route_best_execution(router_with_venues: SmartOrderRouter):
    """BEST_EXECUTION balances price, cost, and reliability."""
    router_with_venues.config.strategy = RoutingStrategy.BEST_EXECUTION
    result = router_with_venues.route("ORD-1", "BBCA.JK", OrderSide.BUY, 100)
    assert result is not None
    assert result.strategy == RoutingStrategy.BEST_EXECUTION
    assert 0 <= result.confidence <= 1


def test_route_twap(router_with_venues: SmartOrderRouter):
    """TWAP splits order into time slices."""
    router_with_venues.config.strategy = RoutingStrategy.TWAP
    router_with_venues.config.twap_slices = 3
    result = router_with_venues.route("ORD-1", "BBCA.JK", OrderSide.BUY, 300)
    assert result is not None
    assert result.strategy == RoutingStrategy.TWAP
    assert len(result.child_orders) == 3
    assert sum(c["quantity"] for c in result.child_orders) == 300


def test_route_vwap(router_with_venues: SmartOrderRouter):
    """VWAP routes based on volume-weighted pricing."""
    router_with_venues.config.strategy = RoutingStrategy.VWAP
    result = router_with_venues.route("ORD-1", "BBCA.JK", OrderSide.BUY, 100)
    assert result is not None
    assert result.strategy == RoutingStrategy.VWAP
    # Should route to venue with highest liquidity
    assert result.venue == "broker_c"  # 10000 ask_size


def test_route_filters_low_reliability(router: SmartOrderRouter):
    """Venues below min_venue_reliability are excluded."""
    router.update_venue_quote(VenueQuote(
        venue="unreliable", bid=89000, ask=89500,
        bid_size=10000, ask_size=10000,
        reliability=0.50,  # Below default 0.90
    ))
    router.update_venue_quote(VenueQuote(
        venue="reliable", bid=90000, ask=90500,
        bid_size=1000, ask_size=1000,
        reliability=0.99,
    ))
    result = router.route("ORD-1", "BBCA.JK", OrderSide.BUY, 100)
    assert result is not None
    assert result.venue == "reliable"


def test_route_returns_none_all_filtered(router: SmartOrderRouter):
    """route returns None when all venues are below reliability threshold."""
    router.update_venue_quote(VenueQuote(
        venue="bad", bid=89000, ask=89500,
        bid_size=100, ask_size=100,
        reliability=0.50,
    ))
    result = router.route("ORD-1", "BBCA.JK", OrderSide.BUY, 100)
    assert result is None


def test_venue_spread():
    """VenueQuote.spread computes correctly."""
    q = VenueQuote(venue="x", bid=100, ask=102, bid_size=100, ask_size=100)
    assert q.spread == 2


def test_routing_decision_has_all_fields(router_with_venues: SmartOrderRouter):
    """RoutingDecision contains all expected fields."""
    result = router_with_venues.route("ORD-1", "BBCA.JK", OrderSide.BUY, 100)
    assert result is not None
    assert result.order_id == "ORD-1"
    assert result.venue != ""
    assert result.quantity == 100
    assert result.expected_price > 0
    assert result.expected_cost > 0
    assert result.estimated_commission >= 0
    assert result.estimated_slippage >= 0
    assert result.reason != ""
    assert result.timestamp != ""


def test_estimate_slippage_large_order(router_with_venues: SmartOrderRouter):
    """Large orders have higher slippage estimate."""
    router_with_venues.config.strategy = RoutingStrategy.BEST_PRICE
    small = router_with_venues.route("ORD-1", "BBCA.JK", OrderSide.BUY, 100)
    large = router_with_venues.route("ORD-2", "BBCA.JK", OrderSide.BUY, 10000)
    assert small is not None
    assert large is not None
    # Large order should have >= slippage
    assert large.estimated_slippage >= small.estimated_slippage


def test_update_venue_quote(router: SmartOrderRouter):
    """update_venue_quote registers and updates venue quotes."""
    router.update_venue_quote(VenueQuote(
        venue="test", bid=100, ask=101, bid_size=100, ask_size=100,
    ))
    assert "test" in router.venues

    # Update
    router.update_venue_quote(VenueQuote(
        venue="test", bid=102, ask=103, bid_size=200, ask_size=200,
    ))
    assert len(router.venues) == 1


def test_twap_remainder_distribution(router_with_venues: SmartOrderRouter):
    """TWAP distributes remainder shares correctly."""
    router_with_venues.config.strategy = RoutingStrategy.TWAP
    router_with_venues.config.twap_slices = 3
    result = router_with_venues.route("ORD-1", "BBCA.JK", OrderSide.BUY, 100)
    assert result is not None
    # 100 / 3 = 33 each, remainder 1 goes to first slice
    quantities = [c["quantity"] for c in result.child_orders]
    assert sum(quantities) == 100
    assert max(quantities) - min(quantities) <= 1
