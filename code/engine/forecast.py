"""
Pure 90-day daily balance simulation engine.

Simulates cash flow day-by-day, tracking reserve requirements and verifying that
the projected balance never dips below minimum_balance_to_keep.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

try:
    from engine.classify_events import CleanUserState, RecurringPattern
except ImportError:
    from code.engine.classify_events import CleanUserState, RecurringPattern


@dataclass(frozen=True)
class PlannedPayment:
    due_date: date
    amount: Decimal


@dataclass(frozen=True)
class SpendingModification:
    event_id: str
    action: str  # 'stop' or 'reduce_to'
    new_amount: Decimal = Decimal(0)


@dataclass(frozen=True)
class SimulationResult:
    is_safe: bool
    lowest_balance: Decimal
    daily_balances: Dict[date, Decimal]
    buffer_ratio: Decimal  # lowest_balance / minimum_balance_to_keep


class BalanceForecaster:
    """90-day pure forecasting engine."""

    HORIZON_DAYS = 90

    @classmethod
    def simulate(
        cls,
        state: CleanUserState,
        start_date: date,
        planned_payments: Optional[List[PlannedPayment]] = None,
        spending_changes: Optional[List[SpendingModification]] = None,
    ) -> SimulationResult:
        """
        Simulates daily balances from start_date to start_date + 90 days.
        """
        payments = planned_payments or []
        changes = spending_changes or []

        # Map spending changes
        stopped_events: Set[str] = {c.event_id for c in changes if c.action == "stop"}
        reduced_events: Dict[str, Decimal] = {c.event_id: c.new_amount for c in changes if c.action == "reduce_to"}

        # Track daily cash delta map
        daily_deltas: Dict[date, Decimal] = {}
        end_date = start_date + timedelta(days=cls.HORIZON_DAYS)

        # 1. Deduct pending debits on their settlement date (or today if past/today)
        for deb in state.pending_debits:
            settle = max(start_date, deb.settlement_date)
            if start_date <= settle <= end_date:
                daily_deltas[settle] = daily_deltas.get(settle, Decimal(0)) - deb.amount

        # 1b. Deduct scheduled debits on their settlement date
        for deb in getattr(state, "scheduled_debits", []):
            if start_date <= deb.settlement_date <= end_date:
                daily_deltas[deb.settlement_date] = daily_deltas.get(deb.settlement_date, Decimal(0)) - deb.amount

        # 2. Add next confirmed salary (and subsequent monthly salary paydays)
        if state.next_confirmed_salary:
            sal = state.next_confirmed_salary
            first_payday = sal.settlement_date
            sal_amt = sal.amount
            if sal_amt and sal_amt > Decimal(0):
                # Apply paydays across the 90-day window
                curr_payday = first_payday
                while curr_payday <= end_date:
                    if curr_payday >= start_date:
                        daily_deltas[curr_payday] = daily_deltas.get(curr_payday, Decimal(0)) + sal_amt
                    # Next month payday (approx 30 days or same day next month)
                    # Use 30-day interval or next month
                    m = curr_payday.month + 1
                    y = curr_payday.year
                    if m > 12:
                        m = 1
                        y += 1
                    # Handle month day capping
                    import calendar
                    max_d = calendar.monthrange(y, m)[1]
                    d = min(first_payday.day, max_d)
                    curr_payday = date(y, m, d)

        # 3. Project recurring expenses
        for pat in state.recurring_expenses:
            ev_id = pat.representative_event_id
            if ev_id in stopped_events:
                continue  # Stopped expense

            cost = pat.amount
            if ev_id in reduced_events:
                cost = reduced_events[ev_id]

            if cost <= Decimal(0):
                continue

            # Determine next occurrence on or after start_date
            # Check pattern typical day of month or interval
            if pat.interval_days >= 25:
                # Monthly occurrence
                import calendar
                curr_month_start = date(start_date.year, start_date.month, 1)
                for month_offset in range(4):
                    m = (start_date.month - 1 + month_offset) % 12 + 1
                    y = start_date.year + ((start_date.month - 1 + month_offset) // 12)
                    max_d = calendar.monthrange(y, m)[1]
                    occ_day = min(pat.typical_day_of_month, max_d)
                    occ_date = date(y, m, occ_day)
                    if start_date <= occ_date <= end_date:
                        daily_deltas[occ_date] = daily_deltas.get(occ_date, Decimal(0)) - cost
            else:
                # Weekly or bi-weekly occurrence
                # Step from pattern anchor date until >= start_date
                step_days = max(1, pat.interval_days)
                import calendar
                anchor_day = min(pat.typical_day_of_month, calendar.monthrange(start_date.year, start_date.month)[1])
                curr_date = date(start_date.year, start_date.month, anchor_day)
                # Walk backward to before start_date if needed
                if curr_date > start_date:
                    steps_back = ((curr_date - start_date).days // step_days) + 1
                    curr_date -= timedelta(days=steps_back * step_days)
                # Walk forward to first occurrence on or after start_date
                while curr_date < start_date:
                    curr_date += timedelta(days=step_days)
                while curr_date <= end_date:
                    daily_deltas[curr_date] = daily_deltas.get(curr_date, Decimal(0)) - cost
                    curr_date += timedelta(days=step_days)

        # 4. Planned candidate payments
        for p in payments:
            if start_date <= p.due_date <= end_date:
                daily_deltas[p.due_date] = daily_deltas.get(p.due_date, Decimal(0)) - p.amount

        # 5. Run daily simulation
        current_bal = state.profile.current_available_balance
        min_balance_needed = state.profile.minimum_balance_to_keep

        lowest_bal = current_bal
        daily_balances: Dict[date, Decimal] = {}

        curr_d = start_date
        while curr_d <= end_date:
            if curr_d in daily_deltas:
                current_bal += daily_deltas[curr_d]
            daily_balances[curr_d] = current_bal
            if current_bal < lowest_bal:
                lowest_bal = current_bal
            curr_d += timedelta(days=1)

        is_safe = lowest_bal >= min_balance_needed
        buffer_ratio = lowest_bal / max(Decimal("1"), min_balance_needed)

        return SimulationResult(
            is_safe=is_safe,
            lowest_balance=lowest_bal,
            daily_balances=daily_balances,
            buffer_ratio=buffer_ratio,
        )

    @classmethod
    def compute_amount_safe_to_pay(
        cls,
        state: CleanUserState,
        requested_amount: Decimal,
        start_date: date,
    ) -> Decimal:
        """
        Compute largest initial payment possible on request_date without spending modifications
        such that all 90 days remain safe. Capped at requested_amount.
        Computed using binary search over valid monetary steps.
        """
        baseline = cls.simulate(state, start_date)
        headroom = baseline.lowest_balance - state.profile.minimum_balance_to_keep
        if headroom <= Decimal(0):
            return Decimal(0)

        max_possible = min(requested_amount, headroom)
        if max_possible <= Decimal(0):
            return Decimal(0)

        # Fast path check: if max_possible is safe directly, return it
        direct_check = cls.simulate(state, start_date, planned_payments=[PlannedPayment(start_date, max_possible)])
        if direct_check.is_safe:
            return max_possible

        # Binary search over monetary steps
        low = Decimal(0)
        high = max_possible
        best_safe = Decimal(0)
        step = Decimal("0.01")

        for _ in range(30):
            mid = ((low + high) / Decimal(2)).quantize(step)
            sim = cls.simulate(state, start_date, planned_payments=[PlannedPayment(start_date, mid)])
            if sim.is_safe:
                best_safe = mid
                low = mid + step
            else:
                high = mid - step
            if low > high:
                break

        return best_safe

    @classmethod
    def compute_earliest_date_for_full_payment(
        cls,
        state: CleanUserState,
        requested_amount: Decimal,
        start_date: date,
    ) -> Optional[date]:
        """
        Find earliest date within 90 days where paying requested_amount in full
        as a single payment is completely safe without spending changes.
        """
        # First check if safe today
        safe_today = cls.compute_amount_safe_to_pay(state, requested_amount, start_date)
        if safe_today >= requested_amount:
            return start_date

        end_date = start_date + timedelta(days=cls.HORIZON_DAYS)

        # Check candidate dates (daily simulation checks)
        curr = start_date
        while curr <= end_date:
            res = cls.simulate(state, start_date, planned_payments=[PlannedPayment(curr, requested_amount)])
            if res.is_safe:
                return curr
            curr += timedelta(days=1)

        return None


def simulate_daily_balances(
    state: CleanUserState,
    start_date: date,
    candidate_payments: Optional[List[PlannedPayment]] = None,
) -> List[Tuple[date, Decimal]]:
    """
    Side-effect-free pure function tracking day-by-day account balances for 90 days.
    Returns list of (date, daily_balance) tuples.
    A day is safe if and only if daily_balance >= minimum_balance_to_keep.
    """
    res = BalanceForecaster.simulate(state, start_date, planned_payments=candidate_payments)
    return [(d, bal) for d, bal in sorted(res.daily_balances.items())]
