from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "schema" / "appointment-request.schema.json"


class RequestSchemaTests(unittest.TestCase):
    def test_schema_is_closed_and_data_minimized(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        properties = set(schema["properties"])

        prohibited = {
            "diagnosis",
            "treatmentNotes",
            "prescriptions",
            "laboratoryResults",
            "radiologyResults",
            "paymentCard",
            "credentials",
            "authenticationSecret",
            "clinicalNotes",
        }

        self.assertFalse(schema["additionalProperties"])
        self.assertTrue(prohibited.isdisjoint(properties))
        self.assertEqual(
            {"patientReference", "appointmentTypeCode", "requestedDate"},
            set(schema["required"]),
        )


if __name__ == "__main__":
    unittest.main()
