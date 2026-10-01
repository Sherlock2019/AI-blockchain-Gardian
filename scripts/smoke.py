#!/usr/bin/env python3
"""Runs the four demo stories against a live stack and checks each outcome.

    make demo            # terminal 1
    python3 scripts/smoke.py [http://127.0.0.1:8000]

Standard library only. Exits non-zero on the first unexpected result.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
CLERK, MANAGER, CFO = "USR-003", "USR-001", "USR-002"


def call(method: str, path: str, user: str, body: dict | None = None) -> tuple[int, dict | list]:
    request = urllib.request.Request(
        f"{BASE}/api{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-User-Id": user},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def expect(label: str, actual: object, wanted: object) -> None:
    ok = actual == wanted
    print(f"  {'ok ' if ok else 'FAIL'} {label}: {actual}")
    if not ok:
        print(f"       expected {wanted}")
        sys.exit(1)


def payment(run: dict) -> dict:
    return next(a for a in run["actions"] if a["action_type"] == "PAY_SUPPLIER")


def main() -> None:
    _, system = call("GET", "/system", CLERK)
    print(f"Ledger: {system['ledger']['mode']} (connected={system['ledger']['connected']}), "
          f"model: {system['llm']['provider']}/{system['llm']['model']}")
    call("POST", "/demo/reset", MANAGER)
    call("POST", "/system/ai-mode", MANAGER, {"enabled": True})

    print("\nDemo 1: analyse, approve, execute, verify")
    _, run = call("POST", "/agent/analyze", CLERK, {"invoice_id": "INV-2026-0042"})
    expect("recommendation", run["recommendation"], "PAYMENT_RECOMMENDED")
    action = payment(run)
    expect("governance", action["decision"]["decision"], "REQUIRE_APPROVAL")
    expect("required role", action["decision"]["required_approval"], "FINANCE_MANAGER")
    status, _ = call("POST", f"/actions/{action['id']}/approve", CLERK, {"comment": ""})
    expect("clerk approval refused", status, 403)
    _, approved = call("POST", f"/actions/{action['id']}/approve", MANAGER, {"comment": "Matches PO"})
    expect("after manager approval", approved["status"], "EXECUTED")
    receipt_id = approved["receipt_id"]
    _, receipt = call("GET", f"/receipts/{receipt_id}", MANAGER)
    expect("anchored", receipt["anchor_status"], "ANCHORED")
    print(f"     tx {receipt['blockchain_tx_hash']} in block {receipt['block_number']}")
    _, verification = call("POST", f"/receipts/{receipt_id}/verify", MANAGER)
    expect("verification", verification["status"], "VERIFIED")

    print("\nDemo 2: tamper with the receipt")
    _, tampered = call("POST", f"/demo/receipts/{receipt_id}/tamper", MANAGER, {"recompute_hash": True})
    expect("amount in database", tampered["amount"], "500000.00")
    _, verification = call("POST", f"/receipts/{receipt_id}/verify", MANAGER)
    expect("database self-consistent", verification["local_match"], True)
    expect("verification", verification["status"], "TAMPER_DETECTED")
    call("POST", f"/demo/receipts/{receipt_id}/restore", MANAGER)

    print("\nDemo 3: prompt injection")
    _, run = call("POST", "/agent/analyze", CLERK, {"invoice_id": "INV-2026-0047"})
    outcome = {a["action_type"]: a["status"] for a in run["actions"]}
    expect("bank account change", outcome.get("CHANGE_SUPPLIER_BANK_ACCOUNT"), "DENIED")
    expect("payment from the same run", outcome.get("PAY_SUPPLIER"), "DENIED")

    print("\nDemo 4: AI off, manual workflow")
    call("POST", "/system/ai-mode", MANAGER, {"enabled": False})
    status, _ = call("POST", "/agent/analyze", CLERK, {"invoice_id": "INV-2026-0048"})
    expect("agent refused", status, 409)
    _, manual = call("POST", "/payments/manual", CLERK, {"invoice_id": "INV-2026-0048"})
    expect("same governance", manual["status"], "PENDING_APPROVAL")
    _, done = call("POST", f"/actions/{manual['id']}/approve", MANAGER, {"comment": ""})
    expect("executed without AI", done["status"], "EXECUTED")
    _, verification = call("POST", f"/receipts/{done['receipt_id']}/verify", MANAGER)
    expect("verification", verification["status"], "VERIFIED")
    call("POST", "/system/ai-mode", MANAGER, {"enabled": True})

    print("\nOther scenarios")
    for invoice, wanted in (
        ("INV-2026-0043", "EXECUTED"),  # $500, autonomous
        ("INV-2026-0045", "DENIED"),  # blocked supplier
        ("INV-2026-0046", "DENIED"),  # exceeds purchase order
        ("INV-2026-0040", "DENIED"),  # duplicate
    ):
        _, run = call("POST", "/agent/analyze", CLERK, {"invoice_id": invoice})
        expect(invoice, payment(run)["status"], wanted)
    _, run = call("POST", "/agent/analyze", CLERK, {"invoice_id": "INV-2026-0044"})
    cfo_action = payment(run)
    expect("INV-2026-0044 requires", cfo_action["decision"]["required_approval"], "CFO")
    status, _ = call("POST", f"/actions/{cfo_action['id']}/approve", MANAGER, {"comment": ""})
    expect("manager refused", status, 403)
    _, done = call("POST", f"/actions/{cfo_action['id']}/approve", CFO, {"comment": ""})
    expect("after CFO approval", done["status"], "EXECUTED")

    _, chain = call("GET", "/audit/verify", MANAGER)
    expect("audit chain intact", chain["intact"], True)
    print("\nAll demo stories behaved as documented.")


if __name__ == "__main__":
    main()
