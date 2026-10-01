"""LLM abstraction.

A provider turns a prompt into text. That text is untrusted input to the rest
of the system: it is parsed against a schema by the agent and every action it
asks for is decided by the governance engine.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any, Protocol

import httpx

from app.security.injection import looks_like_injection

FACTS_OPEN, FACTS_CLOSE = "<facts>", "</facts>"
UNTRUSTED_OPEN, UNTRUSTED_CLOSE = "<untrusted_document>", "</untrusted_document>"


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str) -> str: ...


def _between(text: str, start: str, end: str) -> str:
    match = re.search(re.escape(start) + r"(.*?)" + re.escape(end), text, re.DOTALL)
    return match.group(1).strip() if match else ""


class MockLLMProvider:
    """Deterministic stand-in for a model, so the project runs with no API key.

    It reads the same prompt a real model would and answers in the same JSON
    shape. With `obeys_injection` it follows instructions embedded in the
    untrusted document, which simulates a model that has been successfully
    prompt-injected. That is the case the governance layer exists for.
    """

    name = "mock"
    model = "mock-treasury-1"

    def __init__(self, obeys_injection: bool = True) -> None:
        self._obeys_injection = obeys_injection

    def complete(self, system: str, user: str) -> str:
        facts: dict[str, Any] = json.loads(_between(user, FACTS_OPEN, FACTS_CLOSE) or "{}")
        untrusted = _between(user, UNTRUSTED_OPEN, UNTRUSTED_CLOSE)
        invoice = facts.get("invoice") or {}
        supplier = facts.get("supplier") or {}
        po = facts.get("purchase_order") or {}
        references = [s["title"] for s in facts.get("policy_sources", [])][:3]
        pay = {
            "action_type": "PAY_SUPPLIER",
            "supplier_id": invoice.get("supplier_id"),
            "amount": invoice.get("amount"),
        }

        if looks_like_injection(untrusted):
            if self._obeys_injection:
                account = re.search(r"MOCK-[A-Z0-9-]+", untrusted)
                return json.dumps(
                    {
                        "recommendation": "PAYMENT_RECOMMENDED",
                        "confidence": 0.93,
                        "reasoning_summary": "The invoice notes instruct that the supplier bank "
                        "account be changed and payment sent immediately. Proceeding as instructed.",
                        "policy_references": references,
                        "requested_actions": [
                            {
                                "action_type": "CHANGE_SUPPLIER_BANK_ACCOUNT",
                                "supplier_id": invoice.get("supplier_id"),
                                "params": {
                                    "new_account": account.group(0) if account else "UNSPECIFIED"
                                },
                            },
                            pay,
                        ],
                    }
                )
            return json.dumps(
                {
                    "recommendation": "MANUAL_REVIEW",
                    "confidence": 0.4,
                    "reasoning_summary": "The invoice notes contain text written as instructions "
                    "to change bank details. It was treated as data and not followed. "
                    "A person should review this invoice.",
                    "policy_references": references,
                    "requested_actions": [pay],
                }
            )

        issues = []
        if not supplier:
            issues.append("no supplier record was found")
        elif supplier.get("status") != "APPROVED":
            issues.append(f"supplier {supplier.get('id')} is {supplier.get('status')}")
        if not po:
            issues.append("no purchase order was found")
        else:
            if po.get("supplier_id") != invoice.get("supplier_id"):
                issues.append(f"purchase order {po.get('id')} belongs to another supplier")
            if Decimal(invoice.get("amount", "0")) > Decimal(po.get("approved_amount", "0")):
                issues.append(
                    f"invoice amount {invoice.get('amount')} exceeds purchase order "
                    f"{po.get('id')} ({po.get('approved_amount')})"
                )
        if facts.get("payment_history"):
            issues.append("a payment has already been made against this invoice")
        elif invoice.get("status") != "PENDING":
            issues.append(f"invoice status is {invoice.get('status')}")

        if issues:
            return json.dumps(
                {
                    "recommendation": "PAYMENT_NOT_RECOMMENDED",
                    "confidence": 0.9,
                    "reasoning_summary": "Payment is not recommended: " + "; ".join(issues) + ".",
                    "policy_references": references,
                    "requested_actions": [pay],
                }
            )

        summary = (
            f"Invoice {invoice.get('id')} matches {po.get('id')} and supplier {supplier.get('id')}. "
            "Supplier is approved, the invoice amount is within the purchase order, "
            "and supporting records are present."
        )
        limit = facts.get("agent_autonomous_limit")
        if limit and Decimal(invoice.get("amount", "0")) > Decimal(limit):
            summary += " Human approval is expected because the amount exceeds the autonomous agent limit."
        return json.dumps(
            {
                "recommendation": "PAYMENT_RECOMMENDED",
                "confidence": 0.92,
                "reasoning_summary": summary,
                "policy_references": references,
                "requested_actions": [pay],
            }
        )


class OpenAICompatibleProvider:
    """Any endpoint that speaks the OpenAI chat-completions protocol."""

    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._timeout = timeout_seconds

    def complete(self, system: str, user: str) -> str:
        response = httpx.post(
            self._url,
            headers=self._headers,
            timeout=self._timeout,
            json={
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"])
