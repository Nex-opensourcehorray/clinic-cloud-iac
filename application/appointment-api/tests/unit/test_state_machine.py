from __future__ import annotations

import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from common.state_machine import (  # noqa: E402
    InvalidStateTransition,
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    WorkflowState,
    require_legal_transition,
)


class StateMachineTests(unittest.TestCase):
    def test_accepted_is_http_semantic_not_persisted_state(self) -> None:
        self.assertNotIn("ACCEPTED", {state.value for state in WorkflowState})

    def test_expected_worker_and_reconciliation_transitions_are_legal(self) -> None:
        expected = (
            ("QUEUE_PENDING", "QUEUED"),
            ("QUEUE_PENDING", "PROCESSING"),
            ("QUEUE_PENDING", "RECONCILE_REQUIRED"),
            ("QUEUED", "PROCESSING"),
            ("QUEUED", "RECONCILE_REQUIRED"),
            ("PROCESSING", "FAILED_RETRYABLE"),
            ("PROCESSING", "MANUAL_REVIEW_REQUIRED"),
            ("FAILED_RETRYABLE", "QUEUED"),
            ("FAILED_RETRYABLE", "PROCESSING"),
            ("FAILED_RETRYABLE", "RECONCILE_REQUIRED"),
            ("RECONCILE_REQUIRED", "QUEUED"),
            ("RECONCILE_REQUIRED", "PROCESSING"),
        )
        for current, target in expected:
            with self.subTest(current=current, target=target):
                require_legal_transition(current, target)

    def test_invalid_out_of_order_transition_is_rejected(self) -> None:
        with self.assertRaises(InvalidStateTransition):
            require_legal_transition("QUEUED", "SUCCEEDED")

    def test_same_state_ownership_updates_are_not_business_transitions(self) -> None:
        with self.assertRaises(InvalidStateTransition):
            require_legal_transition("PROCESSING", "PROCESSING")
        with self.assertRaises(InvalidStateTransition):
            require_legal_transition("RECONCILE_REQUIRED", "RECONCILE_REQUIRED")

    def test_terminal_states_have_no_outgoing_transitions(self) -> None:
        self.assertEqual(
            {WorkflowState.MANUAL_REVIEW_REQUIRED, WorkflowState.SUCCEEDED},
            set(TERMINAL_STATES),
        )
        for state in TERMINAL_STATES:
            self.assertEqual(frozenset(), LEGAL_TRANSITIONS[state])

    def test_bounded_invalid_state_names_are_always_rejected(self) -> None:
        for state in (
            "",
            "queued",
            "ACCEPTED",
            "SUCCESS",
            "SUCCEEDED ",
            "PROCESSING\x00",
            "未知状态",
        ):
            with self.subTest(state=state):
                with self.assertRaises(InvalidStateTransition):
                    require_legal_transition(state, "PROCESSING")

    def test_every_undeclared_transition_is_rejected(self) -> None:
        for current in WorkflowState:
            for target in WorkflowState:
                if target in LEGAL_TRANSITIONS[current]:
                    continue
                with self.subTest(current=current.value, target=target.value):
                    with self.assertRaises(InvalidStateTransition):
                        require_legal_transition(current.value, target.value)


if __name__ == "__main__":
    unittest.main()
