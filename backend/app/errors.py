"""Domain errors. API routes translate these to HTTP; services never import FastAPI."""

from __future__ import annotations


class DomainError(Exception):
    code = "DOMAIN_ERROR"
    http_status = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    code = "NOT_FOUND"
    http_status = 404


class ConflictError(DomainError):
    code = "CONFLICT"
    http_status = 409


class ForbiddenError(DomainError):
    code = "FORBIDDEN"
    http_status = 403


class UnauthenticatedError(DomainError):
    code = "UNAUTHENTICATED"
    http_status = 401


class AIDisabledError(ConflictError):
    code = "AI_DISABLED"


class DuplicatePaymentError(ConflictError):
    code = "DUPLICATE_PAYMENT"


class RateLimitedError(DomainError):
    code = "RATE_LIMITED"
    http_status = 429


class LedgerUnavailableError(DomainError):
    """The ledger could not be reached. Retryable."""

    code = "LEDGER_UNAVAILABLE"
    http_status = 503


class LedgerRejectedError(DomainError):
    """The contract refused the transaction. Not retryable without a change of state."""

    code = "LEDGER_REJECTED"
    http_status = 409
