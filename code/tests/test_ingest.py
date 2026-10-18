"""
Unit tests for data ingestion and multi-currency engine.
"""

from datetime import date
from decimal import Decimal
import unittest

import sys
from pathlib import Path

# Ensure 'code' directory is on sys.path for clean submodule imports
code_dir = Path(__file__).resolve().parent.parent
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))

from ingest.load_data import load_all_datasets
from ingest.fx import FXConverter, MissingExchangeRateError


class TestDataIngestion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = load_all_datasets("dataset")

    def test_record_counts(self):
        self.assertEqual(len(self.container.profiles), 275)
        self.assertEqual(len(self.container.events), 25342)
        self.assertEqual(len(self.container.payment_options), 790)
        self.assertEqual(len(self.container.exchange_rates), 134)
        self.assertEqual(len(self.container.messages), 215)
        self.assertEqual(len(self.container.images), 16)
        self.assertEqual(len(self.container.requests), 250)
        self.assertEqual(len(self.container.sample_requests), 25)

    def test_type_safety(self):
        profile = self.container.profiles_by_user_id["user_01"]
        self.assertIsInstance(profile.current_available_balance, Decimal)
        self.assertIsInstance(profile.minimum_balance_to_keep, Decimal)
        self.assertEqual(profile.home_currency, "ZAR")

        req = self.container.requests_by_id["request_26"]
        self.assertIsInstance(req.request_date, date)
        self.assertIsInstance(req.desired_completion_date, date)
        self.assertIsInstance(req.requested_amount, Decimal)

        sample = self.container.sample_requests_by_id["request_01"]
        self.assertIsInstance(sample.amount_safe_to_pay, Decimal)
        self.assertIsInstance(sample.request_date, date)

    def test_lookup_indexing(self):
        self.assertIn("user_01", self.container.events_by_user_id)
        u1_events = self.container.events_by_user_id["user_01"]
        self.assertGreater(len(u1_events), 10)

        # Payment options for request_01
        self.assertIn("request_01", self.container.payment_options_by_request_id)
        opts = self.container.payment_options_by_request_id["request_01"]
        self.assertEqual(len(opts), 4)

        # Images lookup
        self.assertIn("event_253", self.container.images_by_event_id)
        self.assertEqual(self.container.images_by_event_id["event_253"].image_id, "image_01")

        # Lineage lookup
        self.assertIn("event_101", self.container.event_lineage)
        self.assertIn("event_100", self.container.event_lineage["event_101"])

    def test_fx_conversion(self):
        fx = FXConverter(self.container.exchange_rates)

        # Same currency
        rate_same = fx.get_rate("USD", "USD", date(2024, 5, 15))
        self.assertEqual(rate_same, Decimal(1))

        # Direct rate
        rate_eur_zar = fx.get_rate("EUR", "ZAR", date(2024, 3, 20))
        self.assertEqual(rate_eur_zar, Decimal(20))

        # Preceding date rate
        converted = fx.convert(Decimal("100"), "EUR", "ZAR", date(2024, 3, 20))
        self.assertEqual(converted, Decimal("2000"))

        # Inverse rate
        rate_inv = fx.get_rate("EUR", "USD", date(2023, 10, 20))
        self.assertAlmostEqual(float(rate_inv), float(Decimal(1) / Decimal("0.92")), places=4)

        # Non-existent pair error
        with self.assertRaises(MissingExchangeRateError):
            fx.get_rate("NON_EXISTENT", "ZAR", date(2024, 1, 1))


if __name__ == "__main__":
    unittest.main()
