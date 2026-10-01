"""Request bodies. Unknown fields are rejected, not ignored."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

_ID = r"^[A-Za-z0-9][A-Za-z0-9\-]{1,63}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyzeRequest(Strict):
    invoice_id: str = Field(pattern=_ID)


class ManualPaymentRequest(Strict):
    invoice_id: str = Field(pattern=_ID)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    supplier_id: str | None = Field(default=None, pattern=_ID)


class DecisionRequest(Strict):
    comment: str = Field(default="", max_length=500)


class AIModeRequest(Strict):
    enabled: bool


class TamperRequest(Strict):
    recompute_hash: bool = False
