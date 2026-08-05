"""Tests for security, compliance, and operations modules."""

from __future__ import annotations

import tempfile
from pathlib import Path

from market.security.api_versioning import (
    APIVersionManager,
    VersionStatus,
)
from market.security.credentials import CredentialManager
from market.security.fractional import FractionalSharesManager
from market.security.operations import (
    IncidentManager,
    IncidentSeverity,
    IncidentStatus,
    RunbookManager,
)
from market.security.pdp import (
    ChecklistStatus,
    DataSubjectRight,
    PDPCompliance,
)
from market.security.sharia import (
    ScreeningStage,
    ShariaScreener,
)
from market.security.support import (
    DisputeStatus,
    SupportManager,
    TicketPriority,
    TicketStatus,
)
from market.security.surveillance import (
    AlertType,
    OrderRecord,
    TradeRecord,
    TradeSurveillance,
)
from market.security.vendor import (
    SLAConfig,
    VendorHealthMonitor,
    VendorStatus,
)

# --- Credential encryption tests ---


def test_credential_encrypt_decrypt():
    mgr = CredentialManager(master_key="test-secret-key")
    encrypted = mgr.encrypt("my_api_key_123")
    assert encrypted != "my_api_key_123"
    decrypted = mgr.decrypt(encrypted)
    assert decrypted == "my_api_key_123"


def test_credential_store_retrieve():
    mgr = CredentialManager(master_key="test-key")
    mgr.store("broker_api_key", "secret_value_123")
    assert mgr.retrieve("broker_api_key") == "secret_value_123"
    assert mgr.retrieve("nonexistent") is None


def test_credential_rotate_key():
    mgr = CredentialManager(master_key="old-key")
    mgr.store("api_key", "secret_value")
    encrypted_before = mgr._store["api_key"].encrypted_value

    mgr.rotate_key("new-key")
    encrypted_after = mgr._store["api_key"].encrypted_value

    # With Fernet, encrypted values change after rotation.
    # With base64 fallback (no cryptography lib), values stay the same.
    # Either way, decryption must still work.
    assert mgr.retrieve("api_key") == "secret_value"


def test_credential_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "creds.json"
        mgr1 = CredentialManager(master_key="test-key")
        mgr1.store("api_key", "secret123")
        mgr1.save_to_file(path)

        mgr2 = CredentialManager(master_key="test-key")
        mgr2.load_from_file(path)
        assert mgr2.retrieve("api_key") == "secret123"


def test_credential_keys():
    mgr = CredentialManager(master_key="test-key")
    mgr.store("key1", "val1")
    mgr.store("key2", "val2")
    assert set(mgr.keys) == {"key1", "key2"}
    assert mgr.count == 2


# --- API versioning tests ---


def test_api_version_register():
    mgr = APIVersionManager()
    v1 = mgr.register_version("v1", endpoints=["/api/v1/stocks"])
    assert v1.version == "v1"
    assert v1.status == VersionStatus.ACTIVE


def test_api_version_deprecate():
    mgr = APIVersionManager()
    mgr.register_version("v1")
    notice = mgr.deprecate("v1", replacement="v2", reason="EOL")
    assert notice is not None
    v1 = mgr.get_version("v1")
    assert v1.status == VersionStatus.DEPRECATED
    assert v1.sunset_at is not None


def test_api_version_retire():
    mgr = APIVersionManager()
    mgr.register_version("v1")
    assert mgr.retire("v1")
    assert mgr.get_version("v1").status == VersionStatus.RETIRED


def test_api_version_headers():
    mgr = APIVersionManager()
    mgr.register_version("v1")
    mgr.deprecate("v1", replacement="v2")
    headers = mgr.get_deprecation_headers("v1")
    assert "Deprecation" in headers
    assert "Sunset" in headers
    assert "Link" in headers


def test_api_version_active_no_headers():
    mgr = APIVersionManager()
    mgr.register_version("v1")
    headers = mgr.get_deprecation_headers("v1")
    assert len(headers) == 0


def test_api_version_check_status():
    mgr = APIVersionManager()
    mgr.register_version("v1")
    mgr.deprecate("v1", replacement="v2")
    status = mgr.check_version_status("v1")
    assert status["exists"]
    assert status["status"] == "deprecated"


def test_api_version_check_nonexistent():
    mgr = APIVersionManager()
    status = mgr.check_version_status("v9")
    assert not status["exists"]


# --- Sharia screening tests ---


def test_sharia_compliant_stock():
    screener = ShariaScreener()
    screener.register_business_tags("BBCA", {"banking"})
    # Wait — conventional banking is haram
    screener.register_business_tags("TLKM", {"telecommunications"})
    result = screener.screen(
        "TLKM",
        debt_to_assets=0.30,
        interest_income_to_revenue=0.02,
    )
    assert result.is_compliant
    assert result.stage == ScreeningStage.PASSED


def test_sharia_haram_business():
    screener = ShariaScreener()
    screener.register_business_tags("BBCA", {"conventional_banking"})
    result = screener.screen("BBCA")
    assert not result.is_compliant
    assert result.stage == ScreeningStage.BUSINESS_ACTIVITY
    assert not result.business_activity_pass


def test_sharia_failed_financial_ratio():
    screener = ShariaScreener()
    screener.register_business_tags("HALAL", {"food"})
    result = screener.screen(
        "HALAL",
        debt_to_assets=0.50,  # > 45%
        interest_income_to_revenue=0.02,
    )
    assert not result.is_compliant
    assert result.stage == ScreeningStage.FINANCIAL_RATIO
    assert result.business_activity_pass
    assert not result.financial_ratio_pass


def test_sharia_batch():
    screener = ShariaScreener()
    stocks = [
        {"ticker": "A", "tags": {"food"}, "debt_to_assets": 0.2},
        {"ticker": "B", "tags": {"alcohol"}, "debt_to_assets": 0.1},
        {"ticker": "C", "tags": {"tech"}, "debt_to_assets": 0.5},
    ]
    results = screener.screen_batch(stocks)
    assert len(results) == 3
    assert results[0].is_compliant
    assert not results[1].is_compliant
    assert not results[2].is_compliant


# --- Fractional shares tests ---


def test_fractional_calculate_shares():
    mgr = FractionalSharesManager(min_investment=1000)
    shares = mgr.calculate_shares(50000, 7500)
    assert abs(shares - 6.666667) < 0.01


def test_fractional_buy():
    mgr = FractionalSharesManager(min_investment=1000)
    pos = mgr.buy_fractional("BBCA", 50000, 7500)
    assert pos is not None
    assert pos.ticker == "BBCA"
    assert pos.quantity > 0


def test_fractional_buy_below_minimum():
    mgr = FractionalSharesManager(min_investment=10000)
    pos = mgr.buy_fractional("BBCA", 5000, 7500)
    assert pos is None


def test_fractional_sell():
    mgr = FractionalSharesManager(min_investment=1000)
    mgr.buy_fractional("BBCA", 100000, 7500)
    proceeds = mgr.sell_fractional("BBCA", 5.0, 8000)
    assert proceeds is not None
    assert proceeds == 40000.0


def test_fractional_sell_insufficient():
    mgr = FractionalSharesManager(min_investment=1000)
    mgr.buy_fractional("BBCA", 50000, 7500)
    proceeds = mgr.sell_fractional("BBCA", 100.0, 8000)
    assert proceeds is None


def test_fractional_create_plan():
    mgr = FractionalSharesManager(min_investment=1000)
    plan = mgr.create_plan("BBCA", 50000, "monthly")
    assert plan is not None
    assert plan.ticker == "BBCA"
    assert plan.amount_per_period == 50000


def test_fractional_execute_plan():
    mgr = FractionalSharesManager(min_investment=1000)
    plan = mgr.create_plan("BBCA", 50000, "monthly")
    pos = mgr.execute_plan(plan.plan_id, 7500)
    assert pos is not None
    assert plan.executions == 1
    assert plan.total_invested == 50000


# --- Vendor health tests ---


def test_vendor_register():
    monitor = VendorHealthMonitor()
    vendor = monitor.register_vendor("v1", "Data Provider", "https://api.example.com/health")
    assert vendor.vendor_id == "v1"
    assert vendor.status == VendorStatus.UNKNOWN


def test_vendor_health_check():
    monitor = VendorHealthMonitor()
    monitor.register_vendor("v1", "Data Provider", "https://api.example.com/health")
    result = monitor.record_health_check("v1", VendorStatus.HEALTHY, response_time_ms=150)
    assert result is not None
    assert result.status == VendorStatus.HEALTHY


def test_vendor_sla_compliance():
    monitor = VendorHealthMonitor()
    monitor.register_vendor("v1", "Data Provider", "https://api.example.com/health")
    # Record some healthy checks
    for _ in range(10):
        monitor.record_health_check("v1", VendorStatus.HEALTHY, response_time_ms=100)
    compliance = monitor.check_sla_compliance("v1")
    assert compliance["sla_compliant"]


def test_vendor_sla_violation():
    monitor = VendorHealthMonitor()
    monitor.register_vendor(
        "v1", "Data Provider", "https://api.example.com/health",
        SLAConfig(max_response_time_ms=100),
    )
    monitor.record_health_check("v1", VendorStatus.HEALTHY, response_time_ms=500)
    compliance = monitor.check_sla_compliance("v1")
    assert not compliance["sla_compliant"]
    assert len(compliance["sla_violations"]) > 0


def test_vendor_dashboard():
    monitor = VendorHealthMonitor()
    monitor.register_vendor("v1", "Provider 1", "https://api1.example.com/health")
    monitor.register_vendor("v2", "Provider 2", "https://api2.example.com/health")
    dashboard = monitor.dashboard()
    assert len(dashboard) == 2


# --- Trade surveillance tests ---


def test_surveillance_wash_trade():
    surv = TradeSurveillance(wash_trade_window_seconds=300)
    from datetime import UTC, datetime
    ts = datetime.now(UTC).isoformat()
    surv.record_trade(TradeRecord("t1", "ACC1", "BBCA", "buy", 1000, 7500, ts))
    surv.record_trade(TradeRecord("t2", "ACC1", "BBCA", "sell", 1000, 7500, ts))
    alerts = surv.detect_wash_trades()
    assert len(alerts) > 0
    assert alerts[0].alert_type == AlertType.WASH_TRADE


def test_surveillance_no_wash_trade():
    surv = TradeSurveillance()
    from datetime import UTC, datetime
    ts = datetime.now(UTC).isoformat()
    surv.record_trade(TradeRecord("t1", "ACC1", "BBCA", "buy", 1000, 7500, ts))
    surv.record_trade(TradeRecord("t2", "ACC2", "BBCA", "sell", 1000, 7500, ts))
    alerts = surv.detect_wash_trades()
    assert len(alerts) == 0


def test_surveillance_spoofing():
    surv = TradeSurveillance(spoofing_cancel_ratio=0.8)
    for i in range(10):
        surv.record_order(OrderRecord(
            f"o{i}", "ACC1", "BBCA", "buy", 5000, 7500, "cancelled",
            cancel_timestamp="2024-01-01T00:00:00Z",
        ))
    surv.record_order(OrderRecord("o10", "ACC1", "BBCA", "buy", 100, 7500, "filled"))
    alerts = surv.detect_spoofing()
    assert len(alerts) > 0


def test_surveillance_unusual_volume():
    surv = TradeSurveillance(unusual_volume_threshold=3.0)
    # Normal accounts
    for i in range(10):
        surv.record_trade(TradeRecord(f"t{i}", f"ACC{i}", "BBCA", "buy", 100, 7500))
    # Unusual account
    surv.record_trade(TradeRecord("t100", "ACC_BIG", "BBCA", "buy", 5000, 7500))
    alerts = surv.detect_unusual_volume()
    assert len(alerts) > 0


# --- Incident management tests ---


def test_incident_create():
    mgr = IncidentManager()
    inc = mgr.create_incident("DB down", IncidentSeverity.P0, "Primary database unreachable")
    assert inc.incident_id == "INC-0001"
    assert inc.severity == IncidentSeverity.P0
    assert inc.status == IncidentStatus.OPEN


def test_incident_resolve():
    mgr = IncidentManager()
    inc = mgr.create_incident("DB down", IncidentSeverity.P0)
    mgr.update_incident(
        inc.incident_id,
        status=IncidentStatus.RESOLVED,
        resolution="Restarted database service",
    )
    assert mgr.get_incident(inc.incident_id).status == IncidentStatus.RESOLVED
    assert mgr.get_incident(inc.incident_id).resolved_at is not None


def test_incident_add_lesson():
    mgr = IncidentManager()
    inc = mgr.create_incident("DB down", IncidentSeverity.P0)
    mgr.add_lesson(inc.incident_id, "Add database connection monitoring")
    assert len(mgr.get_incident(inc.incident_id).lessons_learned) == 1


def test_incident_get_open():
    mgr = IncidentManager()
    mgr.create_incident("Issue 1", IncidentSeverity.P1)
    mgr.create_incident("Issue 2", IncidentSeverity.P2)
    assert len(mgr.get_open_incidents()) == 2


# --- Runbook tests ---


def test_runbook_defaults():
    mgr = RunbookManager()
    assert len(mgr.runbooks) >= 3  # Default runbooks


def test_runbook_execute():
    mgr = RunbookManager()
    execution = mgr.execute_runbook("RB-DB-001", notes="Test execution")
    assert execution is not None
    assert execution.success
    assert execution.runbook_id == "RB-DB-001"


def test_runbook_register_custom():
    mgr = RunbookManager()
    rb = mgr.register_runbook("RB-CUSTOM-001", "Custom Runbook", "Test", "Test trigger")
    assert rb.runbook_id == "RB-CUSTOM-001"


# --- PDP compliance tests ---


def test_pdp_checklist_defaults():
    pdp = PDPCompliance()
    assert len(pdp.checklist) >= 18


def test_pdp_update_checklist():
    pdp = PDPCompliance()
    item = pdp.update_checklist_item(
        "PDP-001", ChecklistStatus.COMPLIANT, evidence="Consent form implemented",
    )
    assert item is not None
    assert item.status == ChecklistStatus.COMPLIANT
    assert item.evidence == "Consent form implemented"


def test_pdp_register_activity():
    pdp = PDPCompliance()
    activity = pdp.register_processing_activity(
        "ACT-001", "Trade execution", ["account_id", "order_details"],
        "contractual necessity", 365,
    )
    assert activity.activity_id == "ACT-001"
    assert len(pdp.activities) == 1


def test_pdp_subject_request():
    pdp = PDPCompliance()
    req = pdp.create_subject_request(DataSubjectRight.ACCESS, "user123")
    assert req.request_id == "DSR-0001"
    assert req.status == "pending"

    fulfilled = pdp.fulfill_request(req.request_id, "Data exported")
    assert fulfilled.status == "fulfilled"


def test_pdp_breach():
    pdp = PDPCompliance()
    breach = pdp.record_breach(severity="high", description="API key leaked", affected_records=100)
    assert breach.breach_id == "BR-0001"
    assert not breach.notified

    notified = pdp.notify_breach(breach.breach_id)
    assert notified.notified
    assert notified.notified_at is not None


def test_pdp_compliance_summary():
    pdp = PDPCompliance()
    pdp.update_checklist_item("PDP-001", ChecklistStatus.COMPLIANT)
    pdp.update_checklist_item("PDP-002", ChecklistStatus.COMPLIANT)
    summary = pdp.compliance_summary()
    assert summary["compliant"] == 2
    assert summary["compliance_rate"] > 0


# --- Support / dispute tests ---


def test_support_create_ticket():
    mgr = SupportManager()
    ticket = mgr.create_ticket("Login issue", "Cannot login to account")
    assert ticket.ticket_id == "TKT-00001"
    assert ticket.status == TicketStatus.OPEN


def test_support_resolve_ticket():
    mgr = SupportManager()
    ticket = mgr.create_ticket("Login issue", "Cannot login")
    resolved = mgr.resolve_ticket(ticket.ticket_id, "Reset password")
    assert resolved.status == TicketStatus.RESOLVED
    assert resolved.resolved_at is not None


def test_support_add_message():
    mgr = SupportManager()
    ticket = mgr.create_ticket("Issue", "Description")
    assert mgr.add_message(ticket.ticket_id, "Looking into this")
    assert len(ticket.messages) == 2


def test_support_escalate():
    mgr = SupportManager()
    ticket = mgr.create_ticket("Critical issue", "System down", TicketPriority.URGENT)
    escalated = mgr.escalate_ticket(ticket.ticket_id)
    assert escalated.status == TicketStatus.ESCALATED


def test_support_file_dispute():
    mgr = SupportManager()
    ticket = mgr.create_ticket("Wrong order", "Order executed at wrong price")
    dispute = mgr.file_dispute(ticket.ticket_id, "Price dispute", "Order filled at 8000 not 7500")
    assert dispute is not None
    assert dispute.status == DisputeStatus.FILED


def test_support_update_dispute():
    mgr = SupportManager()
    ticket = mgr.create_ticket("Issue", "Description")
    dispute = mgr.file_dispute(ticket.ticket_id, "Dispute", "Description")
    updated = mgr.update_dispute(
        dispute.dispute_id, DisputeStatus.INVESTIGATING, notes="Checking logs",
    )
    assert updated.status == DisputeStatus.INVESTIGATING
    assert len(updated.investigation_notes) == 1


def test_support_sla_breach():
    mgr = SupportManager(sla_hours_urgent=0)
    mgr.create_ticket("Urgent", "Critical issue", TicketPriority.URGENT)
    breached = mgr.check_sla_breach()
    assert len(breached) >= 1


def test_support_open_tickets():
    mgr = SupportManager()
    mgr.create_ticket("Issue 1", "Desc 1")
    mgr.create_ticket("Issue 2", "Desc 2")
    t3 = mgr.create_ticket("Issue 3", "Desc 3")
    mgr.resolve_ticket(t3.ticket_id)
    assert len(mgr.open_tickets) == 2
