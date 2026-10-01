"""The HTTP surface: authentication, validation and the four demo stories."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.container import AppContainer
from app.main import create_app
from tests.conftest import AGENT_ID, ALICE, BOB, CAROL, as_user


def analyze(client: TestClient, invoice_id: str, user: str = CAROL) -> dict:
    response = client.post("/api/agent/analyze", json={"invoice_id": invoice_id}, headers=as_user(user))
    assert response.status_code == 200, response.text
    return response.json()


def payment(run: dict) -> dict:
    return next(a for a in run["actions"] if a["action_type"] == "PAY_SUPPLIER")


# ---- authentication and input validation ------------------------------------

def test_health_needs_no_identity(client):
    assert client.get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"X-User-Id": "USR-999"}])
def test_requests_without_a_known_user_are_refused(client, headers):
    response = client.get("/api/invoices", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHENTICATED"


def test_unknown_fields_and_malformed_ids_are_rejected(client):
    bad_field = client.post(
        "/api/agent/analyze",
        json={"invoice_id": "INV-2026-0042", "amount": 1},
        headers=as_user(CAROL),
    )
    bad_id = client.post(
        "/api/agent/analyze", json={"invoice_id": "'; DROP TABLE"}, headers=as_user(CAROL)
    )
    negative = client.post(
        "/api/payments/manual",
        json={"invoice_id": "INV-2026-0048", "amount": "-5"},
        headers=as_user(CAROL),
    )
    assert [bad_field.status_code, bad_id.status_code, negative.status_code] == [422, 422, 422]


def test_unknown_invoice_is_404_with_a_correlation_id(client):
    response = client.post(
        "/api/agent/analyze", json={"invoice_id": "INV-0000"}, headers=as_user(CAROL)
    )
    assert response.status_code == 404
    assert response.json()["correlation_id"] == response.headers["X-Correlation-ID"]


def test_correlation_id_is_echoed_when_safe_and_replaced_when_not(client):
    kept = client.get("/api/health", headers={"X-Correlation-ID": "demo-run-0001"})
    replaced = client.get("/api/health", headers={"X-Correlation-ID": 'x"}\n{"forged":"log'})
    assert kept.headers["X-Correlation-ID"] == "demo-run-0001"
    assert replaced.headers["X-Correlation-ID"] != 'x"}\n{"forged":"log'


def test_rate_limit(settings):
    container = AppContainer(replace(settings, rate_limit_per_minute=3))
    with TestClient(create_app(container)) as limited:
        codes = [limited.get("/api/invoices", headers=as_user(CAROL)).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


# ---- demo 1: analyse, approve, execute, verify ------------------------------

def test_demo_1_invoice_to_verified_receipt(client):
    run = analyze(client, "INV-2026-0042")
    assert run["recommendation"] == "PAYMENT_RECOMMENDED"
    kinds = {s["kind"] for s in run["retrieved_sources"]}
    assert kinds >= {"invoice", "supplier", "purchase_order", "policy"}
    action = payment(run)
    assert action["status"] == "PENDING_APPROVAL"
    assert action["decision"]["decision"] == "REQUIRE_APPROVAL"
    checks = {c["name"]: c["status"] for c in action["decision"]["policy_checks"]}
    assert checks["supplier_approved"] == "PASS"
    assert checks["autonomous_threshold"] == "ESCALATE"

    pending = client.get("/api/approvals/pending", headers=as_user(ALICE)).json()
    assert [p["id"] for p in pending] == [action["id"]]
    assert pending[0]["analysis"]["recommendation"] == "PAYMENT_RECOMMENDED"

    approved = client.post(
        f"/api/actions/{action['id']}/approve", json={"comment": "Matches PO."}, headers=as_user(ALICE)
    ).json()
    assert approved["status"] == "EXECUTED"
    assert approved["approval"]["user_id"] == ALICE
    assert approved["approval"]["digital_signature_mock"].startswith("mock-hmac-sha256:")

    receipt = client.get(f"/api/receipts/{approved['receipt_id']}", headers=as_user(ALICE)).json()
    assert receipt["amount"] == "50000.00"
    assert receipt["anchor_status"] == "ANCHORED"

    verification = client.post(
        f"/api/receipts/{receipt['receipt_id']}/verify", headers=as_user(ALICE)
    ).json()
    assert verification["status"] == "VERIFIED"

    timeline = client.get(f"/api/agent/runs/{run['run_id']}", headers=as_user(ALICE)).json()["timeline"]
    assert [s["stage"] for s in timeline] == [
        "OBSERVE", "RETRIEVE", "ANALYZE", "RECOMMEND", "GOVERNANCE", "APPROVAL", "EXECUTE", "VERIFY",
    ]
    overview = client.get("/api/overview", headers=as_user(ALICE)).json()
    assert overview["executed_actions"] == 1
    assert overview["verified_receipts"] == 1
    assert overview["pending_approvals"] == 0


def test_approval_beyond_the_users_authority_is_403(client):
    action = payment(analyze(client, "INV-2026-0044"))
    response = client.post(
        f"/api/actions/{action['id']}/approve", json={"comment": ""}, headers=as_user(ALICE)
    )
    assert response.status_code == 403
    assert "CFO is required" in response.json()["message"]
    ok = client.post(f"/api/actions/{action['id']}/approve", json={"comment": ""}, headers=as_user(BOB))
    assert ok.json()["status"] == "EXECUTED"


# ---- demo 2: tamper ---------------------------------------------------------

def test_demo_2_tamper_is_detected(client):
    action = payment(analyze(client, "INV-2026-0043"))
    receipt_id = action["receipt_id"]
    tampered = client.post(
        f"/api/demo/receipts/{receipt_id}/tamper", json={"recompute_hash": True}, headers=as_user(ALICE)
    ).json()
    assert tampered["amount"] == "5000.00"
    assert tampered["tampered_in_demo"] is True

    verification = client.post(f"/api/receipts/{receipt_id}/verify", headers=as_user(ALICE)).json()
    assert verification["status"] == "TAMPER_DETECTED"

    records = client.get("/api/ledger/records", headers=as_user(ALICE)).json()
    assert records[0]["matches"] is False

    client.post(f"/api/demo/receipts/{receipt_id}/restore", headers=as_user(ALICE))
    assert client.post(
        f"/api/receipts/{receipt_id}/verify", headers=as_user(ALICE)
    ).json()["status"] == "VERIFIED"


def test_demo_controls_are_off_outside_demo_mode(settings):
    container = AppContainer(replace(settings, demo_mode=False))
    with TestClient(create_app(container)) as locked:
        for path in ("/api/demo/receipts/RCP-1/tamper", "/api/demo/reset"):
            body = {"recompute_hash": False} if "tamper" in path else None
            assert locked.post(path, json=body, headers=as_user(ALICE)).status_code == 403


# ---- demo 3: prompt injection -----------------------------------------------

def test_demo_3_injected_action_is_denied(client):
    run = analyze(client, "INV-2026-0047")
    statuses = {a["action_type"]: a["status"] for a in run["actions"]}
    assert statuses == {"CHANGE_SUPPLIER_BANK_ACCOUNT": "DENIED", "PAY_SUPPLIER": "DENIED"}
    governance = next(s for s in run["timeline"] if s["stage"] == "GOVERNANCE")
    assert governance["status"] == "BLOCKED"
    assert "CHANGE_SUPPLIER_BANK_ACCOUNT" in governance["detail"]
    assert client.get("/api/metrics", headers=as_user(ALICE)).json()["prompt_injection_blocks"] == 1


# ---- demo 4: AI off ---------------------------------------------------------

def test_demo_4_workflow_survives_without_ai(client):
    clerk_attempt = client.post("/api/system/ai-mode", json={"enabled": False}, headers=as_user(CAROL))
    assert clerk_attempt.status_code == 403

    assert client.post(
        "/api/system/ai-mode", json={"enabled": False}, headers=as_user(ALICE)
    ).json() == {"ai_enabled": False}

    refused = client.post(
        "/api/agent/analyze", json={"invoice_id": "INV-2026-0048"}, headers=as_user(CAROL)
    )
    assert refused.status_code == 409
    assert refused.json()["error"] == "AI_DISABLED"

    manual = client.post(
        "/api/payments/manual", json={"invoice_id": "INV-2026-0048"}, headers=as_user(CAROL)
    ).json()
    assert manual["origin"] == "MANUAL"
    assert manual["status"] == "PENDING_APPROVAL"

    done = client.post(
        f"/api/actions/{manual['id']}/approve", json={"comment": ""}, headers=as_user(ALICE)
    ).json()
    assert done["status"] == "EXECUTED"
    assert client.post(
        f"/api/receipts/{done['receipt_id']}/verify", headers=as_user(ALICE)
    ).json()["status"] == "VERIFIED"


# ---- passport, audit, reset -------------------------------------------------

def test_agent_passport_shows_scope_and_onchain_registration(client):
    passport = client.get(f"/api/agents/{AGENT_ID}/passport", headers=as_user(CAROL)).json()
    assert passport["status"] == "ACTIVE"
    assert passport["autonomous_payment_limit"] == "1000.00"
    assert passport["blockchain"]["registration"] == "VERIFIED"
    assert passport["blockchain"]["ledger_mode"] == "SIMULATED"
    onchain = passport["blockchain"]["onchain_permissions"]
    assert onchain["PROPOSE_PAYMENT"] is True
    assert onchain["CHANGE_SUPPLIER_BANK_ACCOUNT"] is False


def test_audit_trail_is_filterable_and_intact(client):
    response = client.post(
        "/api/agent/analyze",
        json={"invoice_id": "INV-2026-0043"},
        headers={**as_user(CAROL), "X-Correlation-ID": "audit-test-01"},
    )
    assert response.status_code == 200
    events = client.get(
        "/api/audit", params={"correlation_id": "audit-test-01"}, headers=as_user(ALICE)
    ).json()
    assert {"AGENT_RUN_COMPLETED", "GOVERNANCE_ALLOW", "PAYMENT_EXECUTED"} <= {
        e["event_type"] for e in events
    }
    assert client.get("/api/audit/verify", headers=as_user(ALICE)).json()["intact"] is True


def test_demo_reset_restores_seed_state(client):
    analyze(client, "INV-2026-0043")
    assert client.post("/api/demo/reset", headers=as_user(ALICE)).json() == {"status": "reset"}
    invoices = {i["id"]: i for i in client.get("/api/invoices", headers=as_user(ALICE)).json()}
    assert invoices["INV-2026-0043"]["status"] == "PENDING"
    assert client.get("/api/receipts", headers=as_user(ALICE)).json() == []
