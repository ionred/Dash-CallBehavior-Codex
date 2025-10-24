"""CSV validation utilities for account number uploads."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class CsvValidationResult:
    """Represents the result of validating an uploaded CSV file."""

    is_valid: bool
    account_numbers: List[str]
    errors: List[str]


def validate_account_csv(contents: bytes) -> CsvValidationResult:
    """Validate the uploaded CSV file and return the parsed account numbers.

    Args:
        contents: Raw bytes from the uploaded file.

    Returns:
        CsvValidationResult containing the parsed account numbers or errors.
    """

    text_stream = io.StringIO(contents.decode("utf-8-sig"))
    reader = csv.reader(text_stream)

    account_numbers: List[str] = []
    errors: List[str] = []

    for row_number, row in enumerate(reader, start=1):
        if not row:
            errors.append(f"Row {row_number}: empty row detected.")
            continue

        if len(row) != 1:
            errors.append(
                f"Row {row_number}: expected 1 column with the account number, "
                f"found {len(row)} columns."
            )
            continue

        value = row[0].strip()
        if row_number == 1 and not value.isdigit():
            # Treat this as a header row; skip but do not fail validation.
            continue

        if not value:
            errors.append(f"Row {row_number}: account number is blank.")
            continue

        if not value.isdigit():
            errors.append(f"Row {row_number}: account number must contain only digits.")
            continue

        account_numbers.append(value)

    if not account_numbers:
        errors.append("No account numbers were detected in the uploaded file.")

    return CsvValidationResult(
        is_valid=not errors,
        account_numbers=account_numbers,
        errors=errors,
    )


def format_validation_errors(errors: Iterable[str]) -> str:
    """Combine validation error messages into a single display string."""

    return "\n".join(errors)

