"""
Output Generation & Validation Framework - Section 6.3: Automated Validation Assertion Engine (validate/validate_output.py)

Runs strict runtime assertions prior to saving final CSV output:
1. 0 <= amount_safe_to_pay <= requested_amount.
2. Status affordable_now requires earliest_date_for_full_payment == request_date.
3. Method partial_payment requires affordability_status == "affordable_with_plan" and exactly 2 chronological payments totaling requested_amount.
4. Method installments must map to a valid payment_option_id.
5. Dates in payment_plan must be strictly increasing chronological order.
6. spending_changes_needed must not contain duplicate actions or combine stop and reduce for the same event_id.
7. Total row count in output must match requests.csv row count.
8. If any assertion fails, terminate immediately with an error detailing the invalid row.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

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

ALLOWED_STATUSES = {
    "affordable_now",
    "affordable_with_plan",
    "affordable_later",
    "not_affordable",
}

ALLOWED_METHODS = {
    "full_payment",
    "partial_payment",
    "installments",
    "wait",
    "not_recommended",
}


class OutputValidationError(Exception):
    """Raised immediately when any business invariant assertion fails."""
    pass


class OutputValidator:
    """Automated Validation Assertion Engine enforcing all challenge rules."""

    @classmethod
    def load_context_data(
        cls,
        requests_csv_path: str | Path = "dataset/requests.csv",
        options_csv_path: str | Path = "dataset/request_payment_options.csv",
    ) -> Tuple[Dict[str, Tuple[Decimal, date]], Dict[str, Set[str]]]:
        """Loads expected requests (amount, request_date) and valid option IDs."""
        expected_requests: Dict[str, Tuple[Decimal, date]] = {}
        with open(requests_csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rid = r["request_id"].strip()
                amt = Decimal(r["requested_amount"].strip().replace(",", ""))
                d = datetime.strptime(r["request_date"].strip(), "%Y-%m-%d").date()
                expected_requests[rid] = (amt, d)

        valid_options_by_req: Dict[str, Set[str]] = {}
        opts_path = Path(options_csv_path)
        if opts_path.exists():
            with open(opts_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    rid = r["request_id"].strip()
                    op_id = r["payment_option_id"].strip()
                    if rid not in valid_options_by_req:
                        valid_options_by_req[rid] = set()
                    valid_options_by_req[rid].add(op_id)

        return expected_requests, valid_options_by_req

    @classmethod
    def validate_file(
        cls,
        output_csv_path: str | Path,
        requests_csv_path: str | Path = "dataset/requests.csv",
        options_csv_path: str | Path = "dataset/request_payment_options.csv",
        raise_on_error: bool = True,
    ) -> List[str]:
        errors: List[str] = []
        p = Path(output_csv_path)
        if not p.exists():
            msg = f"Output file does not exist: {output_csv_path}"
            if raise_on_error:
                raise OutputValidationError(msg)
            return [msg]

        expected_requests, valid_options = cls.load_context_data(requests_csv_path, options_csv_path)

        with open(p, mode="r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            msg = "Output CSV is empty."
            if raise_on_error:
                raise OutputValidationError(msg)
            return [msg]

        # 1. Header check
        header = rows[0]
        if header != REQUIRED_COLUMNS:
            msg = f"Header mismatch. Expected {REQUIRED_COLUMNS}, got {header}"
            errors.append(msg)
            if raise_on_error:
                raise OutputValidationError(msg)

        data_rows = rows[1:]

        # 7. Total row count in output must match requests.csv row count
        if len(data_rows) != len(expected_requests):
            msg = f"Row count mismatch. Expected {len(expected_requests)} rows, got {len(data_rows)}"
            errors.append(msg)
            if raise_on_error:
                raise OutputValidationError(msg)

        seen_req_ids: Set[str] = set()

        for idx, row in enumerate(data_rows, start=2):
            if len(row) != 8:
                msg = f"Line {idx}: Row does not have exactly 8 columns (found {len(row)}): {row}"
                errors.append(msg)
                if raise_on_error:
                    raise OutputValidationError(msg)
                continue

            (
                req_id,
                safe_str,
                status,
                method,
                plan_str,
                earliest_str,
                changes_str,
                explanation,
            ) = row

            seen_req_ids.add(req_id)

            if req_id not in expected_requests:
                msg = f"Line {idx}: Unknown request_id '{req_id}'"
                errors.append(msg)
                if raise_on_error:
                    raise OutputValidationError(msg)
                continue

            req_amt, req_date = expected_requests[req_id]

            # 1. 0 <= amount_safe_to_pay <= requested_amount
            try:
                safe_amt = Decimal(safe_str)
                if not (Decimal(0) <= safe_amt <= req_amt):
                    msg = f"Line {idx} ({req_id}): amount_safe_to_pay {safe_amt} outside bounds [0, {req_amt}]"
                    errors.append(msg)
                    if raise_on_error:
                        raise OutputValidationError(msg)
            except Exception as e:
                msg = f"Line {idx} ({req_id}): Invalid amount_safe_to_pay '{safe_str}': {e}"
                errors.append(msg)
                if raise_on_error:
                    raise OutputValidationError(msg)

            # Check status
            if status not in ALLOWED_STATUSES:
                msg = f"Line {idx} ({req_id}): Invalid affordability_status '{status}'"
                errors.append(msg)
                if raise_on_error:
                    raise OutputValidationError(msg)

            # Check method
            if method not in ALLOWED_METHODS:
                msg = f"Line {idx} ({req_id}): Invalid recommended_payment_method '{method}'"
                errors.append(msg)
                if raise_on_error:
                    raise OutputValidationError(msg)

            # 2. Status affordable_now requires earliest_date_for_full_payment == request_date
            if status == "affordable_now":
                if not earliest_str:
                    msg = f"Line {idx} ({req_id}): affordable_now requires earliest_date_for_full_payment, but got empty"
                    errors.append(msg)
                    if raise_on_error:
                        raise OutputValidationError(msg)
                else:
                    try:
                        earliest_d = datetime.strptime(earliest_str, "%Y-%m-%d").date()
                        if earliest_d != req_date:
                            msg = f"Line {idx} ({req_id}): affordable_now requires earliest_date_for_full_payment ({earliest_d}) == request_date ({req_date})"
                            errors.append(msg)
                            if raise_on_error:
                                raise OutputValidationError(msg)
                    except ValueError:
                        msg = f"Line {idx} ({req_id}): Malformed earliest_date_for_full_payment '{earliest_str}'"
                        errors.append(msg)
                        if raise_on_error:
                            raise OutputValidationError(msg)

            # 3. Method partial_payment requires affordability_status == "affordable_with_plan" and exactly 2 chronological payments totaling requested_amount
            if method == "partial_payment":
                if status != "affordable_with_plan":
                    msg = f"Line {idx} ({req_id}): partial_payment requires status affordable_with_plan, got '{status}'"
                    errors.append(msg)
                    if raise_on_error:
                        raise OutputValidationError(msg)

                parts = plan_str.split("|")
                if len(parts) != 2:
                    msg = f"Line {idx} ({req_id}): partial_payment requires exactly 2 payments, got {len(parts)} in '{plan_str}'"
                    errors.append(msg)
                    if raise_on_error:
                        raise OutputValidationError(msg)

                try:
                    d1_str, a1_str = parts[0].split(":")
                    d2_str, a2_str = parts[1].split(":")
                    d1 = datetime.strptime(d1_str, "%Y-%m-%d").date()
                    d2 = datetime.strptime(d2_str, "%Y-%m-%d").date()
                    a1 = Decimal(a1_str)
                    a2 = Decimal(a2_str)

                    if d1 >= d2:
                        msg = f"Line {idx} ({req_id}): partial_payment dates must be chronological ({d1} < {d2})"
                        errors.append(msg)
                        if raise_on_error:
                            raise OutputValidationError(msg)

                    if a1 + a2 != req_amt:
                        msg = f"Line {idx} ({req_id}): partial_payment total ({a1 + a2}) does not equal requested_amount ({req_amt})"
                        errors.append(msg)
                        if raise_on_error:
                            raise OutputValidationError(msg)
                except Exception as ex:
                    msg = f"Line {idx} ({req_id}): Invalid partial_payment syntax '{plan_str}': {ex}"
                    errors.append(msg)
                    if raise_on_error:
                        raise OutputValidationError(msg)

            # 4. Method installments must map to a valid payment_option_id
            if method == "installments":
                avail_opts = valid_options.get(req_id, set())
                if not avail_opts:
                    msg = f"Line {idx} ({req_id}): Method installments selected but request has no payment options in request_payment_options.csv"
                    errors.append(msg)
                    if raise_on_error:
                        raise OutputValidationError(msg)

            # 5. Dates in payment_plan must be strictly increasing chronological order
            if plan_str != "none":
                parts = plan_str.split("|")
                prev_date: Optional[date] = None
                for p_idx, part in enumerate(parts):
                    if not re.match(r"^\d{4}-\d{2}-\d{2}:[\d.]+$", part):
                        msg = f"Line {idx} ({req_id}): Malformed payment plan token '{part}'"
                        errors.append(msg)
                        if raise_on_error:
                            raise OutputValidationError(msg)
                        continue

                    d_str, _ = part.split(":")
                    curr_d = datetime.strptime(d_str, "%Y-%m-%d").date()
                    if prev_date is not None and curr_d <= prev_date:
                        msg = f"Line {idx} ({req_id}): payment_plan dates must be strictly increasing chronological order ({prev_date} -> {curr_d})"
                        errors.append(msg)
                        if raise_on_error:
                            raise OutputValidationError(msg)
                    prev_date = curr_d
            else:
                if method not in {"not_recommended", "wait"}:
                    msg = f"Line {idx} ({req_id}): payment_plan cannot be 'none' for method '{method}'"
                    errors.append(msg)
                    if raise_on_error:
                        raise OutputValidationError(msg)

            # 6. spending_changes_needed must not contain duplicate actions or combine stop and reduce for the same event_id
            if changes_str != "none":
                c_parts = changes_str.split("|")
                if len(c_parts) > 3:
                    msg = f"Line {idx} ({req_id}): spending_changes_needed cannot have more than 3 actions, got {len(c_parts)}"
                    errors.append(msg)
                    if raise_on_error:
                        raise OutputValidationError(msg)

                seen_actions: Set[str] = set()
                seen_events: Set[str] = set()
                for c_part in c_parts:
                    if c_part in seen_actions:
                        msg = f"Line {idx} ({req_id}): Duplicate spending change action '{c_part}'"
                        errors.append(msg)
                        if raise_on_error:
                            raise OutputValidationError(msg)

                    seen_actions.add(c_part)

                    if c_part.startswith("stop:"):
                        ev_id = c_part.split(":")[1]
                    elif c_part.startswith("reduce_to:"):
                        ev_id = c_part.split(":")[1]
                    else:
                        msg = f"Line {idx} ({req_id}): Malformed spending change '{c_part}'"
                        errors.append(msg)
                        if raise_on_error:
                            raise OutputValidationError(msg)
                        continue

                    if ev_id in seen_events:
                        msg = f"Line {idx} ({req_id}): Cannot combine stop and reduce for the same event_id '{ev_id}'"
                        errors.append(msg)
                        if raise_on_error:
                            raise OutputValidationError(msg)

                    seen_events.add(ev_id)

            # Explanation non-empty
            if not explanation.strip():
                msg = f"Line {idx} ({req_id}): decision_explanation is empty"
                errors.append(msg)
                if raise_on_error:
                    raise OutputValidationError(msg)

        missing = set(expected_requests.keys()) - seen_req_ids
        if missing:
            msg = f"Missing {len(missing)} expected requests in output: {list(missing)[:5]}..."
            errors.append(msg)
            if raise_on_error:
                raise OutputValidationError(msg)

        return errors


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "output.csv"
    errs = OutputValidator.validate_file(path, raise_on_error=False)
    if errs:
        print(f"Validation FAILED with {len(errs)} errors:")
        for e in errs[:10]:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("Validation PASSED: output.csv is 100% compliant with all challenge rules.")
        sys.exit(0)
