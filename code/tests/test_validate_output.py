"""
Unit tests for output CSV validator and Section 6.3 assertion engine.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest

code_dir = Path(__file__).resolve().parent.parent
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))

from validate.validate_output import OutputValidator, OutputValidationError


class TestOutputValidator(unittest.TestCase):
    def test_existing_output_csv_passes(self):
        output_path = Path("output.csv")
        if output_path.exists():
            errors = OutputValidator.validate_file(
                output_path,
                requests_csv_path="dataset/requests.csv",
                options_csv_path="dataset/request_payment_options.csv",
                raise_on_error=True,
            )
            self.assertEqual(len(errors), 0, f"Expected 0 errors, got: {errors}")

    def test_invalid_bounds_raises_error(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
            tmp.write("request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation\n")
            # safe amount 99999999 > requested amount
            tmp.write("request_26,999999999,affordable_now,full_payment,2025-08-03:15656000,2025-08-03,none,Explanation\n")
            tmp_path = tmp.name

        with self.assertRaises(OutputValidationError):
            OutputValidator.validate_file(tmp_path, requests_csv_path="dataset/requests.csv", raise_on_error=True)

    def test_affordable_now_date_mismatch_raises_error(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
            tmp.write("request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation\n")
            # request_26 request_date is 2025-08-03, here we put 2025-08-04
            tmp.write("request_26,15656000,affordable_now,full_payment,2025-08-03:15656000,2025-08-04,none,Explanation\n")
            tmp_path = tmp.name

        with self.assertRaises(OutputValidationError):
            OutputValidator.validate_file(tmp_path, requests_csv_path="dataset/requests.csv", raise_on_error=True)

    def test_combining_stop_and_reduce_same_event_raises_error(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
            tmp.write("request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation\n")
            # Both stop and reduce on event_100
            tmp.write("request_26,15656000,affordable_with_plan,full_payment,2025-08-03:15656000,2025-08-03,stop:event_100|reduce_to:event_100:50,Explanation\n")
            tmp_path = tmp.name

        with self.assertRaises(OutputValidationError):
            OutputValidator.validate_file(tmp_path, requests_csv_path="dataset/requests.csv", raise_on_error=True)


if __name__ == "__main__":
    unittest.main()
