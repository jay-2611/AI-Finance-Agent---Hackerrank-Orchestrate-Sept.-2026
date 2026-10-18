"""
Deterministic conflict resolution engine based on official challenge priority rules:
1. Explicit cancellations, settlements, or explicit amendments take absolute precedence.
2. Newer updates supersede older updates from the same source.
3. Confirmed/settled transactions supersede forecasts or estimates.
4. If ambiguity remains, choose the financially conservative/safer option (e.g., higher expense, lower income).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

try:
    from ingest.load_data import FinancialEvent
    from extraction.message_extraction import ExtractedMessageIntent
    from extraction.image_extraction import ExtractedImageResult
except ImportError:
    from code.ingest.load_data import FinancialEvent
    from code.extraction.message_extraction import ExtractedMessageIntent
    from code.extraction.image_extraction import ExtractedImageResult


class ConflictResolver:
    """Applies the 4-tier priority rules to resolve conflicting financial records."""

    @classmethod
    def resolve_clean_events(
        cls,
        raw_events: List[FinancialEvent],
        image_data: Dict[str, ExtractedImageResult],
        message_updates: List[ExtractedMessageIntent],
    ) -> List[FinancialEvent]:
        """
        Pass raw event data, extracted image data, and classified message updates
        through the explicit priority order to compute clean events state.
        """
        clean_events: List[FinancialEvent] = []

        # Map images by event_id
        # Step A: Ingest extracted image amounts for blank event amounts
        for ev in raw_events:
            ev_copy = FinancialEvent(
                event_id=ev.event_id,
                user_id=ev.user_id,
                event_type=ev.event_type,
                description=ev.description,
                category=ev.category,
                direction=ev.direction,
                amount=ev.amount,
                currency=ev.currency,
                event_date=ev.event_date,
                settlement_date=ev.settlement_date,
                status=ev.status,
                linked_event_id=ev.linked_event_id,
                flexibility=ev.flexibility,
                minimum_allowed_amount=ev.minimum_allowed_amount,
            )

            # Rule 3: Confirmed/settled image receipts fill missing amounts
            if ev_copy.amount is None and ev_copy.event_id in image_data:
                ev_copy.amount = image_data[ev_copy.event_id].amount
                ev_copy.currency = image_data[ev_copy.event_id].currency

            clean_events.append(ev_copy)

        events_by_id = {e.event_id: e for e in clean_events}

        # Step B: Rule 2 - Sort message updates by sent_at ascending so newer supersede older
        sorted_messages = sorted(message_updates, key=lambda m: getattr(m, "sent_at", ""))

        # Step C: Rule 1 - Explicit cancellations, settlements, amendments take precedence
        for msg in sorted_messages:
            if msg.related_event_id and msg.related_event_id in events_by_id:
                target_ev = events_by_id[msg.related_event_id]
                cls.apply_message_to_event(target_ev, msg)

        return clean_events

    @staticmethod
    def apply_message_to_event(
        event: FinancialEvent,
        intent: ExtractedMessageIntent,
    ) -> FinancialEvent:
        """
        Merge an extracted message intent into a financial event following priority rules.
        """
        if intent.intent == "cancel":
            event.status = "cancelled"
            return event

        if intent.intent == "amend":
            if intent.new_amount is not None:
                event.amount = intent.new_amount
            elif intent.percentage_change is not None and event.amount is not None:
                multiplier = Decimal(1) + (intent.percentage_change / Decimal(100))
                event.amount = (event.amount * multiplier).quantize(Decimal("0.01"))
            if intent.new_date is not None:
                event.settlement_date = intent.new_date
            return event

        if intent.intent == "delay":
            if intent.new_date is not None:
                event.settlement_date = intent.new_date
            return event

        if intent.intent == "confirm":
            if intent.new_amount is not None:
                event.amount = intent.new_amount
            if intent.new_date is not None:
                event.settlement_date = intent.new_date
            if event.status != "settled":
                event.status = "scheduled"
            return event

        return event

    @staticmethod
    def resolve_safer_interpretation(
        direction: str,
        amount_a: Decimal,
        amount_b: Decimal,
    ) -> Decimal:
        """
        Rule 4: If ambiguity remains, choose the financially conservative/safer option:
        - For debits/expenses: higher amount is safer (more conservative headroom).
        - For credits/income: lower amount is safer (avoids relying on unconfirmed cash).
        """
        if direction.lower() == "debit":
            return max(amount_a, amount_b)
        else:
            return min(amount_a, amount_b)
