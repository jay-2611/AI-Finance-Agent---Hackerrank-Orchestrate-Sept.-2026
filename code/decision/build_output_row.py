"""
Output Generation & Validation Framework - Section 6.1: Output Mapping (decision/build_output_row.py)

Map the winning plan to the mandatory 8-column format:
Columns: request_id, amount_safe_to_pay, affordability_status, recommended_payment_method, payment_plan, earliest_date_for_full_payment, spending_changes_needed, decision_explanation.
payment_plan Format: YYYY-MM-DD:amount|YYYY-MM-DD:amount (or none).
spending_changes_needed Format: stop:<event_id> or reduce_to:<event_id>:<amount> (up to 3 pipe-separated entries, or none).

Section 10.2 - Resilience & Risk Index:
- resilience_score: HIGH (balance >= 150% min), MEDIUM (100-149%), CRITICAL (spending changes needed or below 100%)
This field is computed deterministically and stored in DecisionOutcome for internal use / logging.
It must NOT be written to the 8-column submission CSV.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

try:
    from engine.plan_generator import CandidatePlan
    from engine.forecast import SimulationResult
except ImportError:
    from code.engine.plan_generator import CandidatePlan
    from code.engine.forecast import SimulationResult


@dataclass
class DecisionOutcome:
    request_id: str
    amount_safe_to_pay: Decimal
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: Optional[date]
    spending_changes_needed: str
    decision_explanation: str
    # Section 10.2 - Resilience & Risk Index (internal only, NOT in submission CSV)
    resilience_score: str = "CRITICAL"  # HIGH | MEDIUM | CRITICAL
    # Legacy alias kept for backward compatibility
    financial_resilience_tier: str = "CRITICAL_BUFFER"
    lowest_simulated_balance: Optional[Decimal] = None
    min_balance_to_keep: Optional[Decimal] = None


def format_money(val: Decimal) -> str:
    """Format decimal amount: integer if whole, 2 decimal places if fractional cents."""
    if val == val.to_integral_value():
        return str(int(val))
    return f"{val:.2f}"


def format_payment_plan(plan: CandidatePlan) -> str:
    """
    Format payment plan string: <YYYY-MM-DD>:<amount>|<YYYY-MM-DD>:<amount>
    or 'none' if method is not_recommended or wait with no payments.
    """
    if plan.method == "not_recommended" or not plan.payments:
        return "none"

    chunks = []
    for p in sorted(plan.payments, key=lambda x: x.due_date):
        chunks.append(f"{p.due_date.strftime('%Y-%m-%d')}:{format_money(p.amount)}")

    return "|".join(chunks)


def format_spending_changes(plan: CandidatePlan) -> str:
    """
    Format spending changes: stop:<event_id>|reduce_to:<event_id>:<amount>
    or 'none' if no changes needed.
    """
    if not plan.spending_changes:
        return "none"

    chunks = []
    for ch in plan.spending_changes:
        if ch.action == "stop":
            chunks.append(f"stop:{ch.event_id}")
        elif ch.action == "reduce_to":
            chunks.append(f"reduce_to:{ch.event_id}:{format_money(ch.new_amount)}")

    return "|".join(chunks)


def compute_resilience_score(
    simulation: Optional[SimulationResult],
    has_spending_changes: bool,
) -> str:
    """
    Section 10.2 - Resilience & Risk Index Mapping.
    Deterministic computation based on lowest 90-day simulated balance vs minimum_balance_to_keep.

    HIGH:     Balance never drops below 150% of minimum_balance_to_keep.
    MEDIUM:   Balance remains between 100% and 149% of minimum_balance_to_keep.
    CRITICAL: Requires spending reductions OR balance falls below minimum_balance_to_keep.
    """
    if has_spending_changes:
        return "CRITICAL"

    if simulation is None:
        return "CRITICAL"

    if simulation.buffer_ratio >= Decimal("1.50"):
        return "HIGH"
    elif simulation.buffer_ratio >= Decimal("1.00"):
        return "MEDIUM"
    else:
        return "CRITICAL"


def compute_resilience_tier(
    simulation: Optional[SimulationResult],
    has_spending_changes: bool,
) -> str:
    """Legacy alias that maps resilience_score to the old tier naming convention."""
    score = compute_resilience_score(simulation, has_spending_changes)
    mapping = {"HIGH": "HIGH_BUFFER", "MEDIUM": "MODERATE_BUFFER", "CRITICAL": "CRITICAL_BUFFER"}
    return mapping.get(score, "CRITICAL_BUFFER")


def build_output_row(
    request_id: str,
    winning_plan: CandidatePlan,
    amount_safe_today: Decimal,
    earliest_full_date: Optional[date],
    explanation: str,
    min_balance_to_keep: Decimal,
) -> DecisionOutcome:
    """Builds typed DecisionOutcome object with 8-column data + internal resilience metrics."""
    plan_str = format_payment_plan(winning_plan)
    changes_str = format_spending_changes(winning_plan)

    # For affordable_now, earliest_date_for_full_payment must equal request_date
    earliest = earliest_full_date
    if winning_plan.affordability_status == "affordable_now":
        if winning_plan.payments:
            earliest = winning_plan.payments[0].due_date

    has_changes = bool(winning_plan.spending_changes)
    sim = winning_plan.simulation

    # Section 10.2 - compute resilience_score deterministically
    resilience = compute_resilience_score(sim, has_changes)
    # Legacy tier for backward compat
    tier = compute_resilience_tier(sim, has_changes)

    lowest_bal = sim.lowest_balance if sim else None

    return DecisionOutcome(
        request_id=request_id,
        amount_safe_to_pay=amount_safe_today,
        affordability_status=winning_plan.affordability_status,
        recommended_payment_method=winning_plan.method,
        payment_plan=plan_str,
        earliest_date_for_full_payment=earliest,
        spending_changes_needed=changes_str,
        decision_explanation=explanation,
        resilience_score=resilience,
        financial_resilience_tier=tier,
        lowest_simulated_balance=lowest_bal,
        min_balance_to_keep=min_balance_to_keep,
    )