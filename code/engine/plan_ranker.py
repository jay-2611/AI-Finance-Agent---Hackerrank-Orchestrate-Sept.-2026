"""
Deterministic plan ranking engine implementing the official 6-tier tie-breaking hierarchy:
1. Complete the full request by desired_completion_date.
2. Require no spending changes (spending_changes == 0).
3. Minimize the total amount paid (including fees).
4. Start payment earlier (earliest first_payment_date).
5. Use fewer payments (lower num_payments).
6. Lowest payment_option_id as the final tie-breaker.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

try:
    from engine.plan_generator import CandidatePlan
except ImportError:
    from code.engine.plan_generator import CandidatePlan


class PlanRanker:
    """Ranks candidate plans according to strict deterministic priority."""

    @classmethod
    def rank_and_select_best(cls, candidates: List[CandidatePlan]) -> CandidatePlan:
        if not candidates:
            raise ValueError("No candidates provided to rank.")

        # Discard any plan failing simulate() or marked not_recommended
        valid = [
            c for c in candidates
            if c.method != "not_recommended"
            and (c.simulation is None or c.simulation.is_safe)
        ]
        if not valid:
            # Fallback: If no safe candidate plan exists, select recommended_payment_method = "not_recommended"
            fallback = [c for c in candidates if c.method == "not_recommended"]
            if fallback:
                return fallback[0]
            return CandidatePlan(
                plan_id="fallback_not_recommended",
                method="not_recommended",
                affordability_status="not_affordable",
                payments=[],
                spending_changes=[],
                completes_by_deadline=False,
                total_cost=Decimal(0),
                first_payment_date=None,
                num_payments=0,
                simulation=None,
            )

        # Sorting key implementing the 6 rules:
        # Rule 1: completes_by_deadline (True before False -> -int(True))
        # Rule 2: requires no spending changes (len == 0 before len > 0 -> len(spending_changes))
        # Rule 3: minimize total amount paid (total_cost ascending)
        # Rule 4: start payment earlier (first_payment_date ascending)
        # Rule 5: use fewer payments (num_payments ascending)
        # Rule 6: lowest payment_option_id (e.g. 'payment_option_01' < 'payment_option_02')

        def sort_key(plan: CandidatePlan):
            r1 = 0 if plan.completes_by_deadline else 1
            r2 = len(plan.spending_changes)
            r3 = plan.total_cost
            r4 = plan.first_payment_date or date(9999, 12, 31)
            r5 = plan.num_payments
            r6 = plan.payment_option_id or "zzzzzz"
            return (r1, r2, r3, r4, r5, r6)

        sorted_plans = sorted(valid, key=sort_key)
        return sorted_plans[0]
