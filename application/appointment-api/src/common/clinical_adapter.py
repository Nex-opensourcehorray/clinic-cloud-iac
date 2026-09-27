"""Future clinical-system adapter contract; W3.5 provides no live adapter."""

from __future__ import annotations

from enum import Enum
from typing import Protocol


class AdapterOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    NONRETRYABLE_FAILURE = "NONRETRYABLE_FAILURE"
    UNKNOWN_RESULT = "UNKNOWN_RESULT"


class ClinicalAdapter(Protocol):
    def process(self, request_id: str) -> AdapterOutcome:
        """Process only the referenced request and return an explicit outcome."""


class UnavailableClinicalAdapter:
    """Fail-safe W3.5 adapter used until an authoritative integration is approved."""

    def process(self, request_id: str) -> AdapterOutcome:
        del request_id
        return AdapterOutcome.UNKNOWN_RESULT
