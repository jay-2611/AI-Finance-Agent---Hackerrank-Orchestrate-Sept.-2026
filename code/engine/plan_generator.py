"""
Candidate payment plan generator and dynamic what-if counterfactual engine (Section 10.2).

Generates safe, eligible candidate plans (full payment, installments, partial payment,
spending cut trade-offs, delay-to-save waiting) matching user preferences.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
import itertools
from typing import Dict, List, Optional, Tuple

try:
    from ingest.load_data import PaymentOption, Request
    from engine.classify_events import CleanUserState
    from engine.forecast import BalanceForecaster, PlannedPayment, SimulationResult, SpendingModification
except ImportError:
    from code.ingest.load_data import PaymentOption, Request
    from code.engine.classify_events import CleanUserState
    from code.engine.forecast import BalanceForecaster, PlannedPayment, SimulationResult, SpendingModification


@dataclass
class CandidatePlan:
    plan_id: str
    method: str  # full_payment, installments, partial_payment, wait, not_recommended
    affordability_status: str  # affordable_now, affordable_with_plan, affordable_later, not_affordable
    payments: List[PlannedPayment]
    spending_changes: List[SpendingModification] = field(default_factory=list)
    payment_option_id: Optional[str] = None
    completes_by_deadline: bool = True
    total_cost: Decimal = Decimal(0)
    first_payment_date: Optional[date] = None
    num_payments: int = 0
    simulation: Optional[SimulationResult] = None
    counterfactual_notes: str = ""


class PlanGenerator:
    """Generates and evaluates candidate affordability plans."""

    @classmethod
    def generate_all_candidates(
        cls,
        state: CleanUserState,
        req: Request,
        options: List[PaymentOption],
        amount_safe_today: Decimal,
        earliest_full_date: Optional[date],
    ) -> List[CandidatePlan]:
        candidates: List[CandidatePlan] = []
        user_methods = set(state.profile.payment_methods_user_will_consider)

        # 1. Candidate: Full Payment Today without spending changes
        if "full_payment" in user_methods and amount_safe_today >= req.requested_amount:
            p = PlannedPayment(req.request_date, req.requested_amount)
            sim = BalanceForecaster.simulate(state, req.request_date, planned_payments=[p])
            if sim.is_safe:
                candidates.append(CandidatePlan(
                    plan_id="full_today",
                    method="full_payment",
                    affordability_status="affordable_now",
                    payments=[p],
                    spending_changes=[],
                    completes_by_deadline=(req.request_date <= req.desired_completion_date),
                    total_cost=req.requested_amount,
                    first_payment_date=req.request_date,
                    num_payments=1,
                    simulation=sim,
                ))

        # 2. Candidate: Installment Options from request_payment_options.csv
        if "installments" in user_methods:
            max_months = state.profile.max_installment_months or 999
            for opt in options:
                if opt.payment_method != "installments":
                    continue
                # Check installment month duration limit
                freq_days = opt.payment_frequency_days or 30
                total_duration_days = freq_days * (opt.number_of_payments - 1)
                total_months = round(total_duration_days / 30)
                if total_months > max_months:
                    continue

                # Build installment payment schedule
                inst_payments: List[PlannedPayment] = []
                curr_date = opt.first_payment_date
                for _ in range(opt.number_of_payments):
                    inst_payments.append(PlannedPayment(curr_date, opt.payment_amount))
                    curr_date += timedelta(days=freq_days)

                last_payment_date = inst_payments[-1].due_date
                completes = (last_payment_date <= req.desired_completion_date)

                # Test simulation without spending changes
                sim = BalanceForecaster.simulate(state, req.request_date, planned_payments=inst_payments)
                if sim.is_safe:
                    candidates.append(CandidatePlan(
                        plan_id=f"inst_{opt.payment_option_id}",
                        method="installments",
                        affordability_status="affordable_with_plan",
                        payments=inst_payments,
                        spending_changes=[],
                        payment_option_id=opt.payment_option_id,
                        completes_by_deadline=completes,
                        total_cost=opt.total_payable_amount,
                        first_payment_date=opt.first_payment_date,
                        num_payments=opt.number_of_payments,
                        simulation=sim,
                    ))

        # 3. Candidate: Partial Payment (exactly 2 payments)
        # Conditions: allows_partial_payment is True, user considers partial_payment,
        # 0 < amount_safe_to_pay < requested_amount, earliest_date_for_full_payment <= desired_completion_date
        if (
            req.allows_partial_payment
            and "partial_payment" in user_methods
            and Decimal(0) < amount_safe_today < req.requested_amount
            and earliest_full_date is not None
            and earliest_full_date <= req.desired_completion_date
        ):
            p1 = PlannedPayment(req.request_date, amount_safe_today)
            remainder = req.requested_amount - amount_safe_today
            p2 = PlannedPayment(earliest_full_date, remainder)
            sim = BalanceForecaster.simulate(state, req.request_date, planned_payments=[p1, p2])
            if sim.is_safe:
                candidates.append(CandidatePlan(
                    plan_id="partial_2_step",
                    method="partial_payment",
                    affordability_status="affordable_with_plan",
                    payments=[p1, p2],
                    spending_changes=[],
                    completes_by_deadline=(earliest_full_date <= req.desired_completion_date),
                    total_cost=req.requested_amount,
                    first_payment_date=req.request_date,
                    num_payments=2,
                    simulation=sim,
                ))

        # 4. Candidate: Spending Changes (What-If Counterfactual Trade-Offs)
        # If full payment or installment isn't affordable, evaluate up to 3 flexible spending cuts
        # Build list of possible spending modifications
        mod_pool: List[SpendingModification] = []
        for ev_id, pat in state.stoppable_events.items():
            mod_pool.append(SpendingModification(ev_id, "stop", Decimal(0)))
        for ev_id, pat in state.reducible_events.items():
            if pat.minimum_allowed_amount is not None:
                mod_pool.append(SpendingModification(ev_id, "reduce_to", pat.minimum_allowed_amount))

        # Test combinations of 1, 2, or 3 cuts with full payment today
        for k in (1, 2, 3):
            if k > len(mod_pool):
                break
            found_safe_for_k = False
            for combo in itertools.combinations(mod_pool, k):
                # Ensure no duplicate events in combo
                if len(set(c.event_id for c in combo)) < len(combo):
                    continue

                # Test with full payment today
                p_full = [PlannedPayment(req.request_date, req.requested_amount)]
                sim_cut = BalanceForecaster.simulate(
                    state,
                    req.request_date,
                    planned_payments=p_full,
                    spending_changes=list(combo),
                )
                if sim_cut.is_safe and "full_payment" in user_methods:
                    candidates.append(CandidatePlan(
                        plan_id=f"cut_k{k}_{combo[0].event_id}",
                        method="full_payment",
                        affordability_status="affordable_with_plan",
                        payments=p_full,
                        spending_changes=list(combo),
                        completes_by_deadline=(req.request_date <= req.desired_completion_date),
                        total_cost=req.requested_amount,
                        first_payment_date=req.request_date,
                        num_payments=1,
                        simulation=sim_cut,
                    ))
                    found_safe_for_k = True
                    break
            if found_safe_for_k:
                break

        # 5. Candidate: Wait
        # Eligible when full payment becomes safe later and user considers full_payment
        if (
            "full_payment" in user_methods
            and earliest_full_date is not None
            and earliest_full_date > req.request_date
        ):
            p_wait = PlannedPayment(earliest_full_date, req.requested_amount)
            sim_wait = BalanceForecaster.simulate(state, req.request_date, planned_payments=[p_wait])
            completes = (earliest_full_date <= req.desired_completion_date)
            candidates.append(CandidatePlan(
                plan_id="wait_plan",
                method="wait",
                affordability_status="affordable_later",
                payments=[p_wait],
                spending_changes=[],
                completes_by_deadline=completes,
                total_cost=req.requested_amount,
                first_payment_date=earliest_full_date,
                num_payments=1,
                simulation=sim_wait,
            ))

        # 6. Fallback: Not Recommended
        # Fallback when no safe eligible plan exists
        candidates.append(CandidatePlan(
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
        ))

        return candidates
