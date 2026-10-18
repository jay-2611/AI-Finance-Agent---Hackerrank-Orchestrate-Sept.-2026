"""
Unit tests for deterministic 6-tier plan ranking engine.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import unittest

code_dir = Path(__file__).resolve().parent.parent
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))

from engine.plan_generator import CandidatePlan
from engine.plan_ranker import PlanRanker
from engine.forecast import SpendingModification


class TestPlanRanker(unittest.TestCase):
    def test_deadline_priority(self):
        plan_a = CandidatePlan(
            plan_id="plan_a",
            method="installments",
            affordability_status="affordable_with_plan",
            payments=[],
            completes_by_deadline=True,
            total_cost=Decimal("1000"),
        )
        plan_b = CandidatePlan(
            plan_id="plan_b",
            method="full_payment",
            affordability_status="affordable_now",
            payments=[],
            completes_by_deadline=False,
            total_cost=Decimal("800"),  # cheaper, but misses deadline
        )
        best = PlanRanker.rank_and_select_best([plan_a, plan_b])
        self.assertEqual(best.plan_id, "plan_a")

    def test_zero_spending_changes_priority(self):
        plan_no_cut = CandidatePlan(
            plan_id="plan_no_cut",
            method="installments",
            affordability_status="affordable_with_plan",
            payments=[],
            spending_changes=[],
            completes_by_deadline=True,
            total_cost=Decimal("1200"),
        )
        plan_with_cut = CandidatePlan(
            plan_id="plan_with_cut",
            method="full_payment",
            affordability_status="affordable_with_plan",
            payments=[],
            spending_changes=[SpendingModification("ev_sub", "stop")],
            completes_by_deadline=True,
            total_cost=Decimal("1000"),  # cheaper, but requires spending cut
        )
        best = PlanRanker.rank_and_select_best([plan_no_cut, plan_with_cut])
        self.assertEqual(best.plan_id, "plan_no_cut")

    def test_total_cost_priority(self):
        plan_cheap = CandidatePlan(
            plan_id="plan_cheap",
            method="installments",
            affordability_status="affordable_with_plan",
            payments=[],
            spending_changes=[],
            completes_by_deadline=True,
            total_cost=Decimal("1050"),
        )
        plan_expensive = CandidatePlan(
            plan_id="plan_expensive",
            method="installments",
            affordability_status="affordable_with_plan",
            payments=[],
            spending_changes=[],
            completes_by_deadline=True,
            total_cost=Decimal("1200"),
        )
        best = PlanRanker.rank_and_select_best([plan_cheap, plan_expensive])
        self.assertEqual(best.plan_id, "plan_cheap")

    def test_tie_breaker_lowest_option_id(self):
        plan_opt1 = CandidatePlan(
            plan_id="opt1",
            method="installments",
            affordability_status="affordable_with_plan",
            payments=[],
            spending_changes=[],
            payment_option_id="payment_option_01",
            completes_by_deadline=True,
            total_cost=Decimal("1000"),
            first_payment_date=date(2026, 9, 10),
            num_payments=3,
        )
        plan_opt2 = CandidatePlan(
            plan_id="opt2",
            method="installments",
            affordability_status="affordable_with_plan",
            payments=[],
            spending_changes=[],
            payment_option_id="payment_option_02",
            completes_by_deadline=True,
            total_cost=Decimal("1000"),
            first_payment_date=date(2026, 9, 10),
            num_payments=3,
        )
        best = PlanRanker.rank_and_select_best([plan_opt2, plan_opt1])
        self.assertEqual(best.payment_option_id, "payment_option_01")


if __name__ == "__main__":
    unittest.main()
