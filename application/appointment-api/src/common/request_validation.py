"""Defense-in-depth validation for the minimized appointment request."""

from __future__ import annotations

import re
from typing import Any


_REQUIRED_FIELDS = {"patientReference", "appointmentTypeCode", "requestedDate"}
_OPTIONAL_FIELDS = {"timePreference", "locationCode", "contactPreference"}
_OPAQUE_REFERENCE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_CODE = re.compile(r"^[A-Z0-9_-]{1,40}$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_TIME_PREFERENCES = {"MORNING", "AFTERNOON", "EVENING", "ANY"}
_CONTACT_PREFERENCES = {"PHONE", "EMAIL", "SMS"}


class RequestValidationError(Exception):
    """The authenticated body does not match the minimized request contract."""


def validate_request_document(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise RequestValidationError("Request body must be an object")

    fields = set(document)
    if not _REQUIRED_FIELDS.issubset(fields):
        raise RequestValidationError("Required request fields are missing")
    if not fields.issubset(_REQUIRED_FIELDS | _OPTIONAL_FIELDS):
        raise RequestValidationError("Unexpected request fields are prohibited")

    patient_reference = document.get("patientReference")
    appointment_type = document.get("appointmentTypeCode")
    requested_date = document.get("requestedDate")
    if not isinstance(patient_reference, str) or not _OPAQUE_REFERENCE.fullmatch(
        patient_reference
    ):
        raise RequestValidationError("Invalid patient reference")
    if not isinstance(appointment_type, str) or not _CODE.fullmatch(appointment_type):
        raise RequestValidationError("Invalid appointment type")
    if not isinstance(requested_date, str) or not _DATE.fullmatch(requested_date):
        raise RequestValidationError("Invalid requested date")

    time_preference = document.get("timePreference")
    if time_preference is not None and time_preference not in _TIME_PREFERENCES:
        raise RequestValidationError("Invalid time preference")

    location_code = document.get("locationCode")
    if location_code is not None and (
        not isinstance(location_code, str) or not _CODE.fullmatch(location_code)
    ):
        raise RequestValidationError("Invalid location code")

    contact_preference = document.get("contactPreference")
    if (
        contact_preference is not None
        and contact_preference not in _CONTACT_PREFERENCES
    ):
        raise RequestValidationError("Invalid contact preference")

    return document
