from __future__ import annotations

import random
import string
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

    def test_rejects_prohibited_payment_credential_and_contact_fields(self) -> None:
        for field in (
            "clinicalNotes",
            "freeText",
            "paymentCard",
            "password",
            "credential",
            "emailAddress",
            "phoneNumber",
        ):
            with self.subTest(field=field):
                document = self.valid()
                document[field] = "SYNTHETIC-PROHIBITED-VALUE"
                with self.assertRaises(RequestValidationError):
                    validate_request_document(document)

    def test_empty_optional_values_and_unusual_unicode_fail_closed(self) -> None:
        for field, value in (
            ("timePreference", ""),
            ("locationCode", ""),
            ("contactPreference", ""),
            ("patientReference", "患者"),
            ("appointmentTypeCode", "CONSULT-☃"),
        ):
            with self.subTest(field=field, value=value):
                document = self.valid()
                document[field] = value
                with self.assertRaises(RequestValidationError):
                    validate_request_document(document)

    def test_bounded_random_additional_fields_are_rejected(self) -> None:
        generator = random.Random(3702)
        for _ in range(32):
            field = "x_" + "".join(
                generator.choice(string.ascii_letters) for _ in range(12)
            )
            document = self.valid()
            document[field] = "synthetic"
            with self.subTest(field=field):
                with self.assertRaises(RequestValidationError):
                    validate_request_document(document)


if __name__ == "__main__":
    unittest.main()
