"""
CSV serialization module writing output.csv in the exact required 8-column schema.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Union

try:
    from decision.build_output_row import DecisionOutcome
except ImportError:
    from code.decision.build_output_row import DecisionOutcome

REQUIRED_COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]


def write_submission_csv(
    outcomes: List[DecisionOutcome],
    output_path: Union[str, Path] = "output.csv",
) -> None:
    """
    Writes predictions to output_path adhering strictly to the official 8-column schema.
    """
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with open(p, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        # 1. Header
        writer.writerow(REQUIRED_COLUMNS)

        # 2. Rows in exact order
        for item in outcomes:
            earliest_str = (
                item.earliest_date_for_full_payment.strftime("%Y-%m-%d")
                if item.earliest_date_for_full_payment
                else ""
            )
            # Format decimal without scientific notation or unnecessary trailing zeros
            safe_str = f"{item.amount_safe_to_pay:f}".rstrip("0").rstrip(".") if "." in f"{item.amount_safe_to_pay:f}" else str(item.amount_safe_to_pay)
            if safe_str == "":
                safe_str = "0"

            row = [
                item.request_id,
                safe_str,
                item.affordability_status,
                item.recommended_payment_method,
                item.payment_plan,
                earliest_str,
                item.spending_changes_needed,
                item.decision_explanation,
            ]
            writer.writerow(row)
