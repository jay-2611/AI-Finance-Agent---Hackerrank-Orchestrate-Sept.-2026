import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

code_dir = Path(__file__).resolve().parent.parent
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))

from engine.classify_events import EventClassifier, AnnotatedEvent
from ingest.load_data import FinancialProfile, FinancialEvent, UserMessage
from ingest.fx import FXConverter, ExchangeRate


class TestEventClassification(unittest.TestCase):
    def setUp(self):
        self.profile = FinancialProfile(
            user_id="user_test",
            home_currency="USD",
            current_available_balance=Decimal("5000.00"),
            minimum_balance_to_keep=Decimal("1000.00"),
            financial_priorities=["debt_payoff", "savings"],
            expense_categories_to_protect=["rent", "utilities"],
            expense_categories_user_is_willing_to_reduce=["dining"],
            expense_categories_user_is_willing_to_stop=["streaming", "gym"],
            payment_methods_user_will_consider=["full_payment", "installments"],
            max_installment_months=6,
        )

        self.fx = FXConverter([])

        # Sample events
        self.ev_rent = FinancialEvent(
            event_id="ev_01",
            user_id="user_test",
            event_type="expense",
            description="Monthly Apartment Rent",
            category="rent",
            direction="debit",
            amount=Decimal("1200.00"),
            currency="USD",
            event_date=date(2026, 9, 1),
            settlement_date=date(2026, 9, 1),
            status="settled",
            linked_event_id=None,
            flexibility="fixed",
            minimum_allowed_amount=None,
        )

        self.ev_streaming = FinancialEvent(
            event_id="ev_02",
            user_id="user_test",
            event_type="subscription",
            description="Video Streaming Plan",
            category="streaming",
            direction="debit",
            amount=Decimal("15.99"),
            currency="USD",
            event_date=date(2026, 9, 5),
            settlement_date=date(2026, 9, 5),
            status="settled",
            linked_event_id=None,
            flexibility="stoppable",
            minimum_allowed_amount=None,
        )

        self.ev_dining = FinancialEvent(
            event_id="ev_03",
            user_id="user_test",
            event_type="expense",
            description="Weekend Restaurant Dinner",
            category="dining",
            direction="debit",
            amount=Decimal("120.00"),
            currency="USD",
            event_date=date(2026, 9, 6),
            settlement_date=date(2026, 9, 6),
            status="settled",
            linked_event_id=None,
            flexibility="reducible",
            minimum_allowed_amount=Decimal("50.00"),
        )

        self.ev_shopping = FinancialEvent(
            event_id="ev_04",
            user_id="user_test",
            event_type="expense",
            description="One-off electronics purchase",
            category="shopping",
            direction="debit",
            amount=Decimal("250.00"),
            currency="USD",
            event_date=date(2026, 9, 7),
            settlement_date=date(2026, 9, 7),
            status="settled",
            linked_event_id=None,
            flexibility="fixed",
            minimum_allowed_amount=None,
        )

        self.ev_pending = FinancialEvent(
            event_id="ev_05",
            user_id="user_test",
            event_type="expense",
            description="Pending card authorization",
            category="shopping",
            direction="debit",
            amount=Decimal("80.00"),
            currency="USD",
            event_date=date(2026, 9, 8),
            settlement_date=date(2026, 9, 10),
            status="pending",
            linked_event_id=None,
            flexibility="fixed",
            minimum_allowed_amount=None,
        )

        self.ev_cancelled = FinancialEvent(
            event_id="ev_06",
            user_id="user_test",
            event_type="expense",
            description="Cancelled hotel booking",
            category="travel",
            direction="debit",
            amount=Decimal("400.00"),
            currency="USD",
            event_date=date(2026, 9, 9),
            settlement_date=date(2026, 9, 9),
            status="cancelled",
            linked_event_id=None,
            flexibility="fixed",
            minimum_allowed_amount=None,
        )

        self.ev_unrealized = FinancialEvent(
            event_id="ev_07",
            user_id="user_test",
            event_type="investment_valuation",
            description="Quarterly portfolio value update",
            category="investment",
            direction="non_cash",
            amount=Decimal("15000.00"),
            currency="USD",
            event_date=date(2026, 9, 10),
            settlement_date=date(2026, 9, 10),
            status="unrealized",
            linked_event_id=None,
            flexibility="fixed",
            minimum_allowed_amount=None,
        )

        # Duplicate event identical to ev_shopping
        self.ev_duplicate = FinancialEvent(
            event_id="ev_08",
            user_id="user_test",
            event_type="expense",
            description="One-off electronics purchase",
            category="shopping",
            direction="debit",
            amount=Decimal("250.00"),
            currency="USD",
            event_date=date(2026, 9, 7),
            settlement_date=date(2026, 9, 7),
            status="settled",
            linked_event_id=None,
            flexibility="fixed",
            minimum_allowed_amount=None,
        )

    def test_structured_attributes_annotation(self):
        events = [
            self.ev_rent,
            self.ev_streaming,
            self.ev_dining,
            self.ev_shopping,
            self.ev_pending,
            self.ev_cancelled,
            self.ev_unrealized,
            self.ev_duplicate,
        ]

        state = EventClassifier.reconstruct_user_state(
            profile=self.profile,
            raw_events=events,
            messages=[],
            fx_converter=self.fx,
            request_date=date(2026, 9, 8),
        )

        # Check all events are annotated
        self.assertEqual(len(state.annotated_events), 8)
        by_id = {ae.event_id: ae for ae in state.annotated_events}

        # Frequency checks
        self.assertEqual(by_id["ev_01"].frequency, "recurring")
        self.assertEqual(by_id["ev_02"].frequency, "recurring")
        self.assertEqual(by_id["ev_03"].frequency, "recurring")
        self.assertEqual(by_id["ev_04"].frequency, "one_time")

        # Flexibility checks cross-referenced with user spending tier
        self.assertEqual(by_id["ev_01"].flexibility, "essential")  # rent is protected
        self.assertEqual(by_id["ev_02"].flexibility, "flexible")   # streaming is stoppable & user willing
        self.assertEqual(by_id["ev_03"].flexibility, "flexible")   # dining is reducible & user willing
        self.assertEqual(by_id["ev_04"].flexibility, "essential")  # shopping is fixed

        # Lifecycle status checks
        self.assertEqual(by_id["ev_01"].lifecycle_status, "confirmed")
        self.assertEqual(by_id["ev_05"].lifecycle_status, "pending")
        self.assertEqual(by_id["ev_06"].lifecycle_status, "cancelled")
        self.assertEqual(by_id["ev_07"].lifecycle_status, "unrealized_investment")
        self.assertEqual(by_id["ev_08"].lifecycle_status, "duplicate")

        # RULE CHECK: Cancelled, duplicate, and unrealized investments must be excluded
        valid_event_ids = {e.event_id for e in state.events}
        self.assertNotIn("ev_06", valid_event_ids, "Cancelled event must be excluded")
        self.assertNotIn("ev_07", valid_event_ids, "Unrealized investment must be excluded")
        self.assertNotIn("ev_08", valid_event_ids, "Duplicate event must be excluded")

        # Pending debit must be in pending_debits
        pending_ids = {e.event_id for e in state.pending_debits}
        self.assertIn("ev_05", pending_ids)


if __name__ == "__main__":
    unittest.main()
