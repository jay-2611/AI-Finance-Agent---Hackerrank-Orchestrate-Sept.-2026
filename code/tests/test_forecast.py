"""
Unit tests for 90-day balance forecast simulation engine.
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import sys
import unittest

code_dir = Path(__file__).resolve().parent.parent
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))

from ingest.load_data import FinancialEvent, FinancialProfile
from engine.classify_events import CleanUserState, RecurringPattern
from engine.forecast import BalanceForecaster, PlannedPayment


class TestForecastEngine(unittest.TestCase):
    def setUp(self):
        self.profile = FinancialProfile(
            user_id="test_user",
            home_currency="USD",
            current_available_balance=Decimal("5000.00"),
            minimum_balance_to_keep=Decimal("1000.00"),
            financial_priorities=["emergency_savings"],
            expense_categories_to_protect=["rent"],
            expense_categories_user_is_willing_to_reduce=[],
            expense_categories_user_is_willing_to_stop=[],
            payment_methods_user_will_consider=["full_payment"],
            max_installment_months=None,
        )

        # Recurring rent: $1500 on day 1
        rent_pattern = RecurringPattern(
            pattern_id="pat_rent",
            description="Apartment rent",
            category="rent",
            direction="debit",
            amount=Decimal("1500.00"),
            currency="USD",
            typical_day_of_month=1,
            interval_days=30,
            flexibility="fixed",
            minimum_allowed_amount=None,
            representative_event_id="ev_rent",
        )

        self.salary = FinancialEvent(
            event_id="ev_salary",
            user_id="test_user",
            event_type="income",
            description="Salary",
            category="salary",
            direction="credit",
            amount=Decimal("3000.00"),
            currency="USD",
            event_date=date(2026, 9, 15),
            settlement_date=date(2026, 9, 15),
            status="scheduled",
            linked_event_id=None,
            flexibility="fixed",
            minimum_allowed_amount=None,
        )

        self.state = CleanUserState(
            user_id="test_user",
            profile=self.profile,
            events=[],
            recurring_expenses=[rent_pattern],
            recurring_incomes=[],
            pending_debits=[],
            next_confirmed_salary=self.salary,
            stoppable_events={},
            reducible_events={},
        )

    def test_baseline_simulation_is_safe(self):
        res = BalanceForecaster.simulate(self.state, date(2026, 9, 2))
        self.assertTrue(res.is_safe)
        self.assertGreaterEqual(res.lowest_balance, Decimal("1000.00"))

    def test_headroom_and_safe_amount(self):
        # Requested amount: 2000
        safe_amt = BalanceForecaster.compute_amount_safe_to_pay(
            self.state,
            requested_amount=Decimal("2000.00"),
            start_date=date(2026, 9, 2),
        )
        self.assertGreater(safe_amt, Decimal(0))
        self.assertLessEqual(safe_amt, Decimal("2000.00"))

    def test_buffer_ratio_and_tier(self):
        res = BalanceForecaster.simulate(self.state, date(2026, 9, 2))
        self.assertGreater(res.buffer_ratio, Decimal("1.00"))


if __name__ == "__main__":
    unittest.main()
