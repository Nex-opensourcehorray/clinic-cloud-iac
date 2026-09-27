from __future__ import annotations

import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from common.request_validation import (  # noqa: E402
    RequestValidationError,
    validate_request_document,
)


class RequestValidationTests(unittest.TestCase):
    def valid(self):
        return {
            "patientReference": "SYNTHETIC-PATIENT-001",
            "appointmentTypeCode": "GENERAL_CONSULT",
            "requestedDate": "2030-01-15",
        }

    def test_accepts_minimized_document(self) -> None:
        self.assertEqual(self.valid(), validate_request_document(self.valid()))

    def test_rejects_unrestricted_clinical_free_text(self) -> None:
        document = self.valid()
        document["clinicalNotes"] = "synthetic prohibited text"
        with self.assertRaises(RequestValidationError):
            validate_request_document(document)

    def test_rejects_missing_required_field(self) -> None:
        document = self.valid()
        del document["patientReference"]
        with self.assertRaises(RequestValidationError):
            validate_request_document(document)


if __name__ == "__main__":
    unittest.main()
