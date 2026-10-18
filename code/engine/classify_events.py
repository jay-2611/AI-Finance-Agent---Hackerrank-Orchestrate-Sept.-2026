"""
Event classification and clean state reconstruction module.

Categorizes events into recurring vs one-time, essential vs flexible,
and incorporates image and message evidence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

try:
    from ingest.load_data import FinancialEvent, FinancialProfile, UserMessage
    from extraction.image_extraction import extract_from_image
    from extraction.message_extraction import MessageExtractor, ExtractedMessageIntent
    from extraction.conflict_resolution import ConflictResolver
    from ingest.fx import FXConverter
except ImportError:
    from code.ingest.load_data import FinancialEvent, FinancialProfile, UserMessage
    from code.extraction.image_extraction import extract_from_image
    from code.extraction.message_extraction import MessageExtractor, ExtractedMessageIntent
    from code.extraction.conflict_resolution import ConflictResolver
    from code.ingest.fx import FXConverter


@dataclass
class RecurringPattern:
    pattern_id: str
    description: str
    category: str
    direction: str  # credit, debit
    amount: Decimal
    currency: str
    typical_day_of_month: int
    interval_days: int
    flexibility: str  # fixed, reducible, stoppable
    minimum_allowed_amount: Optional[Decimal]
    representative_event_id: str


@dataclass
class AnnotatedEvent:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str  # credit, debit, non_cash
    amount: Optional[Decimal]
    currency: str
    event_date: date
    settlement_date: date
    raw_status: str
    raw_flexibility: str
    minimum_allowed_amount: Optional[Decimal]
    frequency: str  # 'recurring' vs 'one_time'
    flexibility: str  # 'flexible' vs 'essential' (cross-referenced with user spending tier)
    lifecycle_status: str  # 'confirmed' | 'pending' | 'cancelled' | 'duplicate' | 'unrealized_investment'
    raw_event: FinancialEvent


@dataclass
class CleanUserState:
    user_id: str
    profile: FinancialProfile
    events: List[FinancialEvent]
    recurring_expenses: List[RecurringPattern]
    recurring_incomes: List[RecurringPattern]
    pending_debits: List[FinancialEvent]
    next_confirmed_salary: Optional[FinancialEvent]
    stoppable_events: Dict[str, RecurringPattern]
    reducible_events: Dict[str, RecurringPattern]
    annotated_events: List[AnnotatedEvent] = field(default_factory=list)
    scheduled_debits: List[FinancialEvent] = field(default_factory=list)


class EventClassifier:
    """Classifies clean financial events and detects recurring patterns."""

    @classmethod
    def reconstruct_user_state(
        cls,
        profile: FinancialProfile,
        raw_events: List[FinancialEvent],
        messages: List[UserMessage],
        fx_converter: FXConverter,
        request_date: date,
    ) -> CleanUserState:
        import calendar

        # 1. Clean copy of events with multimodal image resolution and FX conversion
        events: List[FinancialEvent] = []
        for ev in raw_events:
            # Fill missing amount from image if blank
            amt = ev.amount
            if amt is None:
                try:
                    img_res = extract_from_image(ev.event_id)
                    amt = img_res.amount
                except Exception:
                    amt = Decimal(0)

            # Normalize foreign currency to home_currency
            if amt is not None and ev.currency != profile.home_currency:
                amt = fx_converter.convert(amt, ev.currency, profile.home_currency, ev.settlement_date)
                curr = profile.home_currency
            else:
                curr = ev.currency

            clean_ev = replace(ev, amount=amt, currency=curr)
            events.append(clean_ev)

        # 2. Apply message modifications and track explicit cancellation intents
        msg_intents = [MessageExtractor.parse_message(m) for m in messages if m.user_id == profile.user_id]
        events_by_id = {e.event_id: e for e in events}
        cancelled_by_msg: Set[str] = set()

        for intent in msg_intents:
            if intent.related_event_id and intent.related_event_id in events_by_id:
                ev = events_by_id[intent.related_event_id]
                ConflictResolver.apply_message_to_event(ev, intent)
                if intent.intent == "cancel":
                    cancelled_by_msg.add(intent.related_event_id)

        # Detect duplicate records (same user, description, amount, date, direction)
        seen_events: Set[Tuple[str, str, Optional[Decimal], date, str]] = set()
        duplicate_ids: Set[str] = set()
        for e in events:
            sig = (e.user_id, e.description, e.amount, e.event_date, e.direction)
            if sig in seen_events:
                duplicate_ids.add(e.event_id)
            else:
                seen_events.add(sig)

        # 3. Annotate every clean event with Frequency, Flexibility, and Lifecycle Status
        annotated_events: List[AnnotatedEvent] = []
        for e in events:
            # Frequency: recurring vs one_time
            is_recurring = False
            if e.event_type in {"subscription", "debt_payment"} or e.category in {
                "rent", "utilities", "salary", "insurance", "cloud_storage",
                "streaming", "music_subscription", "delivery_membership", "gym", "housing"
            }:
                is_recurring = True
            elif e.flexibility in {"stoppable", "reducible", "reducible_or_stoppable"}:
                is_recurring = True
            frequency = "recurring" if is_recurring else "one_time"

            # Flexibility: flexible vs essential (cross-referencing user spending tier in financial_profiles.csv)
            is_protected = e.category in profile.expense_categories_to_protect
            is_flex = False
            if not is_protected:
                if (
                    e.flexibility in {"stoppable", "reducible_or_stoppable"}
                    and e.category in profile.expense_categories_user_is_willing_to_stop
                ):
                    is_flex = True
                elif (
                    e.flexibility in {"reducible", "reducible_or_stoppable"}
                    and e.category in profile.expense_categories_user_is_willing_to_reduce
                    and e.minimum_allowed_amount is not None
                ):
                    is_flex = True
            flexibility = "flexible" if is_flex else "essential"

            # Lifecycle Status: confirmed | pending | cancelled | duplicate | unrealized_investment
            if e.event_id in cancelled_by_msg or e.status in {"cancelled", "failed"}:
                lifecycle = "cancelled"
            elif e.status == "unrealized" or e.direction == "non_cash" or e.event_type == "investment_valuation":
                lifecycle = "unrealized_investment"
            elif e.event_id in duplicate_ids:
                lifecycle = "duplicate"
            elif e.status == "pending":
                lifecycle = "pending"
            else:
                lifecycle = "confirmed"

            annotated_events.append(AnnotatedEvent(
                event_id=e.event_id,
                user_id=e.user_id,
                event_type=e.event_type,
                description=e.description,
                category=e.category,
                direction=e.direction,
                amount=e.amount,
                currency=e.currency,
                event_date=e.event_date,
                settlement_date=e.settlement_date,
                raw_status=e.status,
                raw_flexibility=e.flexibility,
                minimum_allowed_amount=e.minimum_allowed_amount,
                frequency=frequency,
                flexibility=flexibility,
                lifecycle_status=lifecycle,
                raw_event=e,
            ))

        # 4. Filter valid cash events strictly excluding cancelled, duplicate, and unrealized_investment
        # RULE: Events tagged as cancelled, duplicate, or unrealized_investment must be completely excluded.
        valid_events = [
            ae.raw_event for ae in annotated_events
            if ae.lifecycle_status not in {"cancelled", "duplicate", "unrealized_investment"}
            and ae.amount is not None
            and ae.amount > Decimal(0)
        ]

        # 5. Pending debits near request_date
        pending_debits = [
            ae.raw_event for ae in annotated_events
            if ae.lifecycle_status == "pending"
            and ae.direction.lower() == "debit"
            and ae.amount is not None
            and ae.amount > Decimal(0)
        ]

        # Scheduled future debits
        scheduled_debits = [
            ae.raw_event for ae in annotated_events
            if ae.lifecycle_status == "confirmed"
            and ae.raw_status == "scheduled"
            and ae.direction.lower() == "debit"
            and ae.amount is not None
            and ae.amount > Decimal(0)
            and ae.settlement_date >= request_date
        ]

        # 6. Next confirmed salary & employer message overrides
        employer_intents = [
            intent for intent in msg_intents
            if intent.user_id == profile.user_id
        ]

        salary_cancelled = any(
            intent.intent == "cancel" for intent in employer_intents
        )

        next_salary: Optional[FinancialEvent] = None
        if not salary_cancelled:
            # Check candidate salary events with settlement_date >= request_date
            salary_candidates = [
                e for e in valid_events
                if e.category == "salary"
                and e.direction.lower() == "credit"
                and e.settlement_date >= request_date
            ]

            if salary_candidates:
                salary_candidates.sort(key=lambda s: s.settlement_date)
                next_salary = salary_candidates[0]
            else:
                # Find historical regular salaries
                past_salaries = [
                    e for e in valid_events
                    if e.category == "salary"
                    and e.direction.lower() == "credit"
                    and "bonus" not in e.description.lower()
                    and "arrears" not in e.description.lower()
                ]
                if past_salaries:
                    past_salaries.sort(key=lambda s: s.settlement_date, reverse=True)
                    latest_past = past_salaries[0]

                    # Determine regular payday (most common day of month among regular salaries, defaults to 15)
                    day_counts: Dict[int, int] = defaultdict(int)
                    for s in past_salaries:
                        day_counts[s.settlement_date.day] += 1
                    regular_payday = max(day_counts.keys(), key=lambda d: day_counts[d])

                    # Determine target month & year
                    if request_date.day <= regular_payday:
                        t_year, t_month = request_date.year, request_date.month
                    else:
                        t_month = request_date.month + 1
                        t_year = request_date.year
                        if t_month > 12:
                            t_month = 1
                            t_year += 1
                    max_d = calendar.monthrange(t_year, t_month)[1]
                    next_date = date(t_year, t_month, min(regular_payday, max_d))

                    next_salary = FinancialEvent(
                        event_id=f"proj_sal_{profile.user_id}",
                        user_id=profile.user_id,
                        event_type="income",
                        description="Projected recurring confirmed salary",
                        category="salary",
                        direction="credit",
                        amount=latest_past.amount,
                        currency=latest_past.currency,
                        event_date=next_date,
                        settlement_date=next_date,
                        status="scheduled",
                        linked_event_id=None,
                        flexibility="fixed",
                        minimum_allowed_amount=None,
                    )

            # Apply employer message overrides if any
            if next_salary:
                for intent in employer_intents:
                    if intent.new_amount is not None:
                        next_salary.amount = intent.new_amount
                        if intent.currency:
                            next_salary.currency = intent.currency
                    if intent.new_date is not None:
                        next_salary.settlement_date = intent.new_date

        # 7. Group historical recurring events from confirmed recurring annotated events
        groups = defaultdict(list)
        for ae in annotated_events:
            if (
                ae.frequency == "recurring"
                and ae.lifecycle_status == "confirmed"
                and ae.raw_event.event_date <= request_date
                and ae.amount is not None
                and ae.amount > Decimal(0)
            ):
                key = (ae.category, ae.description, ae.direction.lower())
                groups[key].append(ae.raw_event)

        recurring_expenses: List[RecurringPattern] = []
        recurring_incomes: List[RecurringPattern] = []
        stoppable_events: Dict[str, RecurringPattern] = {}
        reducible_events: Dict[str, RecurringPattern] = {}

        for (category, desc, direction), ev_list in groups.items():
            ev_list.sort(key=lambda x: x.event_date)
            latest = ev_list[-1]

            typical_day = latest.settlement_date.day
            interval = 30
            if len(ev_list) >= 2:
                intervals = [(ev_list[i].event_date - ev_list[i-1].event_date).days for i in range(1, len(ev_list))]
                interval = max(7, round(sum(intervals) / len(intervals)))

            pat = RecurringPattern(
                pattern_id=f"pat_{latest.event_id}",
                description=desc,
                category=category,
                direction=direction,
                amount=latest.amount,
                currency=latest.currency,
                typical_day_of_month=typical_day,
                interval_days=interval,
                flexibility=latest.flexibility,
                minimum_allowed_amount=latest.minimum_allowed_amount,
                representative_event_id=latest.event_id,
            )

            if direction == "debit":
                recurring_expenses.append(pat)
                # Check user profile willingness
                is_protected = category in profile.expense_categories_to_protect
                if not is_protected:
                    if (
                        latest.flexibility in {"stoppable", "reducible_or_stoppable"}
                        and category in profile.expense_categories_user_is_willing_to_stop
                    ):
                        stoppable_events[latest.event_id] = pat
                    if (
                        latest.flexibility in {"reducible", "reducible_or_stoppable"}
                        and category in profile.expense_categories_user_is_willing_to_reduce
                        and latest.minimum_allowed_amount is not None
                    ):
                        reducible_events[latest.event_id] = pat
            else:
                if category == "salary":
                    recurring_incomes.append(pat)

        return CleanUserState(
            user_id=profile.user_id,
            profile=profile,
            events=valid_events,
            recurring_expenses=recurring_expenses,
            recurring_incomes=recurring_incomes,
            pending_debits=pending_debits,
            next_confirmed_salary=next_salary,
            stoppable_events=stoppable_events,
            reducible_events=reducible_events,
            annotated_events=annotated_events,
            scheduled_debits=scheduled_debits,
        )
