"""
Unit tests for interactive ambiguity clarifier layer (Section 10.1).
"""

from decimal import Decimal
from pathlib import Path
import sys
import unittest

code_dir = Path(__file__).resolve().parent.parent
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))

from extraction.interactive_clarifier import InteractiveClarifier, ClarificationRequest


class TestInteractiveClarifier(unittest.TestCase):
    def test_high_confidence_auto_commit(self):
        clarifier = InteractiveClarifier(interactive_mode=False)
        res = clarifier.evaluate_and_clarify(
            event_id="ev_101",
            best_guess_amount=Decimal("150.00"),
            currency="USD",
            confidence=0.98,
            issue_description="Clear receipt",
        )
        self.assertEqual(res.committed_amount, Decimal("150.00"))
        self.assertEqual(res.source, "high_confidence_auto")
        self.assertFalse(res.was_clarified)

    def test_low_confidence_triggers_clarification(self):
        clarifier = InteractiveClarifier(interactive_mode=False)
        res = clarifier.evaluate_and_clarify(
            event_id="ev_102",
            best_guess_amount=Decimal("89.99"),
            currency="USD",
            confidence=0.82,  # < 90%
            issue_description="Blurry watermark near total",
        )
        self.assertEqual(res.committed_amount, Decimal("89.99"))
        self.assertEqual(res.source, "autonomous_best_guess")


if __name__ == "__main__":
    unittest.main()
