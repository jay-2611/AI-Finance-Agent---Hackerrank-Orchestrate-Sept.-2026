"""
Dataset ingestion and normalization module for the 'Buy or Wait?' financial agent system.

Converts all dates strictly to datetime.date and all monetary values strictly to decimal.Decimal.
Builds fast indexing lookup maps and transaction lifecycle lineage structures.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional, Union


def parse_date(value: Optional[str]) -> Optional[date]:
    """Parse a date string formatted as YYYY-MM-DD."""
    if not value or not value.strip():
        return None
    val = value.strip()
    # If full ISO datetime timestamp (e.g. 2025-07-29T09:30:00Z)
    if "T" in val:
        val = val.split("T")[0]
    return datetime.strptime(val, "%Y-%m-%d").date()


def parse_decimal(value: Optional[str]) -> Optional[Decimal]:
    """Parse a monetary or decimal string without floating point conversion."""
    if value is None:
        return None
    val = str(value).strip().replace(",", "")
    if not val:
        return None
    try:
        return Decimal(val)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid monetary decimal string: {value!r}") from exc


def parse_list(value: Optional[str], delimiter: str = "|") -> list[str]:
    """Parse pipe-separated strings into a list of cleaned tokens."""
    if not value or not value.strip():
        return []
    return [item.strip() for item in value.strip().split(delimiter) if item.strip()]


def parse_bool(value: Optional[str]) -> bool:
    """Parse boolean flag ('true', 'false', '1', '0')."""
    if not value:
        return False
    return value.strip().lower() in {"true", "1", "yes", "t"}


def parse_int(value: Optional[str]) -> Optional[int]:
    """Parse optional integer."""
    if not value or not value.strip():
        return None
    return int(float(value.strip()))


@dataclass(frozen=True)
class FinancialProfile:
    user_id: str
    home_currency: str
    current_available_balance: Decimal
    minimum_balance_to_keep: Decimal
    financial_priorities: list[str]
    expense_categories_to_protect: list[str]
    expense_categories_user_is_willing_to_reduce: list[str]
    expense_categories_user_is_willing_to_stop: list[str]
    payment_methods_user_will_consider: list[str]
    max_installment_months: Optional[int]


@dataclass
class FinancialEvent:
    event_id: str
    user_id: str
    event_type: str  # expense, income, subscription, debt_payment, refund, investment
    description: str
    category: str
    direction: str  # credit, debit
    amount: Optional[Decimal]  # May be None initially if extraction from receipt required
    currency: str
    event_date: date
    settlement_date: date
    status: str  # settled, pending, scheduled, cancelled, failed, unrealized
    linked_event_id: Optional[str]
    flexibility: str  # fixed, reducible, stoppable
    minimum_allowed_amount: Optional[Decimal]


@dataclass(frozen=True)
class PaymentOption:
    payment_option_id: str
    request_id: str
    payment_method: str  # full_payment, installments
    payment_amount: Decimal
    number_of_payments: int
    first_payment_date: date
    payment_frequency_days: Optional[int]
    financing_fee: Decimal
    total_payable_amount: Decimal


@dataclass(frozen=True)
class ExchangeRate:
    rate_date: date
    from_currency: str
    to_currency: str
    rate: Decimal


@dataclass(frozen=True)
class UserMessage:
    message_id: str
    user_id: str
    request_id: Optional[str]
    related_event_id: Optional[str]
    sent_at: str
    source_type: str  # employer, bank, service_provider, merchant, financial_service
    message_text: str


@dataclass(frozen=True)
class ImageRecord:
    image_id: str
    user_id: str
    request_id: Optional[str]
    related_event_id: str


@dataclass(frozen=True)
class Request:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: Decimal
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str


@dataclass(frozen=True)
class SampleRequest:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: Decimal
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str
    amount_safe_to_pay: Decimal
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: Optional[date]
    spending_changes_needed: str
    decision_explanation: str


@dataclass
class DatasetContainer:
    profiles: list[FinancialProfile] = field(default_factory=list)
    events: list[FinancialEvent] = field(default_factory=list)
    payment_options: list[PaymentOption] = field(default_factory=list)
    exchange_rates: list[ExchangeRate] = field(default_factory=list)
    messages: list[UserMessage] = field(default_factory=list)
    images: list[ImageRecord] = field(default_factory=list)
    requests: list[Request] = field(default_factory=list)
    sample_requests: list[SampleRequest] = field(default_factory=list)

    # Fast indexing lookup structures
    profiles_by_user_id: dict[str, FinancialProfile] = field(default_factory=dict)
    events_by_id: dict[str, FinancialEvent] = field(default_factory=dict)
    events_by_user_id: dict[str, list[FinancialEvent]] = field(default_factory=dict)
    events_by_linked_id: dict[str, list[FinancialEvent]] = field(default_factory=dict)
    event_lineage: dict[str, list[str]] = field(default_factory=dict)

    messages_by_id: dict[str, UserMessage] = field(default_factory=dict)
    messages_by_user_id: dict[str, list[UserMessage]] = field(default_factory=dict)
    messages_by_event_id: dict[str, list[UserMessage]] = field(default_factory=dict)
    messages_by_request_id: dict[str, list[UserMessage]] = field(default_factory=dict)

    payment_options_by_request_id: dict[str, list[PaymentOption]] = field(default_factory=dict)
    payment_options_by_id: dict[str, PaymentOption] = field(default_factory=dict)

    images_by_id: dict[str, ImageRecord] = field(default_factory=dict)
    images_by_event_id: dict[str, ImageRecord] = field(default_factory=dict)
    images_by_request_id: dict[str, ImageRecord] = field(default_factory=dict)

    requests_by_id: dict[str, Request] = field(default_factory=dict)
    sample_requests_by_id: dict[str, SampleRequest] = field(default_factory=dict)


def load_all_datasets(dataset_dir: Union[str, Path] = "dataset") -> DatasetContainer:
    """
    Load all dataset CSVs from dataset_dir into a fully normalized,
    typed, and indexed DatasetContainer.
    """
    base_path = Path(dataset_dir)
    container = DatasetContainer()

    # 1. Financial Profiles
    profiles_path = base_path / "financial_profiles.csv"
    if profiles_path.exists():
        with open(profiles_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                profile = FinancialProfile(
                    user_id=row["user_id"].strip(),
                    home_currency=row["home_currency"].strip(),
                    current_available_balance=parse_decimal(row["current_available_balance"]) or Decimal(0),
                    minimum_balance_to_keep=parse_decimal(row["minimum_balance_to_keep"]) or Decimal(0),
                    financial_priorities=parse_list(row.get("financial_priorities")),
                    expense_categories_to_protect=parse_list(row.get("expense_categories_to_protect")),
                    expense_categories_user_is_willing_to_reduce=parse_list(row.get("expense_categories_user_is_willing_to_reduce")),
                    expense_categories_user_is_willing_to_stop=parse_list(row.get("expense_categories_user_is_willing_to_stop")),
                    payment_methods_user_will_consider=parse_list(row.get("payment_methods_user_will_consider")),
                    max_installment_months=parse_int(row.get("max_installment_months")),
                )
                container.profiles.append(profile)
                container.profiles_by_user_id[profile.user_id] = profile

    # 2. Financial Events
    events_path = base_path / "financial_events.csv"
    if events_path.exists():
        with open(events_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                event_date = parse_date(row["event_date"])
                settlement_date = parse_date(row["settlement_date"]) or event_date
                assert event_date is not None
                assert settlement_date is not None

                linked_id = row.get("linked_event_id", "").strip() or None
                event = FinancialEvent(
                    event_id=row["event_id"].strip(),
                    user_id=row["user_id"].strip(),
                    event_type=row["event_type"].strip(),
                    description=row["description"].strip(),
                    category=row["category"].strip(),
                    direction=row["direction"].strip(),
                    amount=parse_decimal(row.get("amount")),
                    currency=row["currency"].strip(),
                    event_date=event_date,
                    settlement_date=settlement_date,
                    status=row["status"].strip(),
                    linked_event_id=linked_id,
                    flexibility=row["flexibility"].strip(),
                    minimum_allowed_amount=parse_decimal(row.get("minimum_allowed_amount")),
                )
                container.events.append(event)
                container.events_by_id[event.event_id] = event

                if event.user_id not in container.events_by_user_id:
                    container.events_by_user_id[event.user_id] = []
                container.events_by_user_id[event.user_id].append(event)

                if linked_id:
                    if linked_id not in container.events_by_linked_id:
                        container.events_by_linked_id[linked_id] = []
                    container.events_by_linked_id[linked_id].append(event)

        # Build transaction lineage
        for event in container.events:
            lineage = [event.event_id]
            curr = event.linked_event_id
            while curr and curr in container.events_by_id:
                lineage.append(curr)
                curr = container.events_by_id[curr].linked_event_id
            container.event_lineage[event.event_id] = lineage

    # 3. Request Payment Options
    options_path = base_path / "request_payment_options.csv"
    if options_path.exists():
        with open(options_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                first_date = parse_date(row["first_payment_date"])
                assert first_date is not None
                option = PaymentOption(
                    payment_option_id=row["payment_option_id"].strip(),
                    request_id=row["request_id"].strip(),
                    payment_method=row["payment_method"].strip(),
                    payment_amount=parse_decimal(row["payment_amount"]) or Decimal(0),
                    number_of_payments=int(row["number_of_payments"]),
                    first_payment_date=first_date,
                    payment_frequency_days=parse_int(row.get("payment_frequency_days")),
                    financing_fee=parse_decimal(row["financing_fee"]) or Decimal(0),
                    total_payable_amount=parse_decimal(row["total_payable_amount"]) or Decimal(0),
                )
                container.payment_options.append(option)
                container.payment_options_by_id[option.payment_option_id] = option
                if option.request_id not in container.payment_options_by_request_id:
                    container.payment_options_by_request_id[option.request_id] = []
                container.payment_options_by_request_id[option.request_id].append(option)

    # 4. Exchange Rates
    rates_path = base_path / "exchange_rates.csv"
    if rates_path.exists():
        with open(rates_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                r_date = parse_date(row["rate_date"])
                assert r_date is not None
                rate = ExchangeRate(
                    rate_date=r_date,
                    from_currency=row["from_currency"].strip(),
                    to_currency=row["to_currency"].strip(),
                    rate=parse_decimal(row["rate"]) or Decimal(1),
                )
                container.exchange_rates.append(rate)

    # 5. Messages
    messages_path = base_path / "messages.csv"
    if messages_path.exists():
        with open(messages_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                req_id = row.get("request_id", "").strip() or None
                ev_id = row.get("related_event_id", "").strip() or None
                msg = UserMessage(
                    message_id=row["message_id"].strip(),
                    user_id=row["user_id"].strip(),
                    request_id=req_id,
                    related_event_id=ev_id,
                    sent_at=row["sent_at"].strip(),
                    source_type=row["source_type"].strip(),
                    message_text=row["message_text"].strip(),
                )
                container.messages.append(msg)
                container.messages_by_id[msg.message_id] = msg

                if msg.user_id not in container.messages_by_user_id:
                    container.messages_by_user_id[msg.user_id] = []
                container.messages_by_user_id[msg.user_id].append(msg)

                if ev_id:
                    if ev_id not in container.messages_by_event_id:
                        container.messages_by_event_id[ev_id] = []
                    container.messages_by_event_id[ev_id].append(msg)

                if req_id:
                    if req_id not in container.messages_by_request_id:
                        container.messages_by_request_id[req_id] = []
                    container.messages_by_request_id[req_id].append(msg)

    # 6. Images metadata
    images_path = base_path / "images.csv"
    if images_path.exists():
        with open(images_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                req_id = row.get("request_id", "").strip() or None
                ev_id = row["related_event_id"].strip()
                img = ImageRecord(
                    image_id=row["image_id"].strip(),
                    user_id=row["user_id"].strip(),
                    request_id=req_id,
                    related_event_id=ev_id,
                )
                container.images.append(img)
                container.images_by_id[img.image_id] = img
                container.images_by_event_id[ev_id] = img
                if req_id:
                    container.images_by_request_id[req_id] = img

    # 7. Requests (Evaluation targets)
    requests_path = base_path / "requests.csv"
    if requests_path.exists():
        with open(requests_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                req_date = parse_date(row["request_date"])
                comp_date = parse_date(row["desired_completion_date"])
                assert req_date is not None
                assert comp_date is not None
                req = Request(
                    request_id=row["request_id"].strip(),
                    user_id=row["user_id"].strip(),
                    request_date=req_date,
                    request_type=row["request_type"].strip(),
                    requested_amount=parse_decimal(row["requested_amount"]) or Decimal(0),
                    desired_completion_date=comp_date,
                    allows_partial_payment=parse_bool(row["allows_partial_payment"]),
                    request_text=row["request_text"].strip(),
                )
                container.requests.append(req)
                container.requests_by_id[req.request_id] = req

    # 8. Sample Requests (Ground Truth Reference)
    sample_path = base_path / "sample_requests.csv"
    if sample_path.exists():
        with open(sample_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                req_date = parse_date(row["request_date"])
                comp_date = parse_date(row["desired_completion_date"])
                earliest_date = parse_date(row.get("earliest_date_for_full_payment"))
                assert req_date is not None
                assert comp_date is not None
                sample = SampleRequest(
                    request_id=row["request_id"].strip(),
                    user_id=row["user_id"].strip(),
                    request_date=req_date,
                    request_type=row["request_type"].strip(),
                    requested_amount=parse_decimal(row["requested_amount"]) or Decimal(0),
                    desired_completion_date=comp_date,
                    allows_partial_payment=parse_bool(row["allows_partial_payment"]),
                    request_text=row["request_text"].strip(),
                    amount_safe_to_pay=parse_decimal(row["amount_safe_to_pay"]) or Decimal(0),
                    affordability_status=row["affordability_status"].strip(),
                    recommended_payment_method=row["recommended_payment_method"].strip(),
                    payment_plan=row["payment_plan"].strip(),
                    earliest_date_for_full_payment=earliest_date,
                    spending_changes_needed=row["spending_changes_needed"].strip(),
                    decision_explanation=row["decision_explanation"].strip(),
                )
                container.sample_requests.append(sample)
                container.sample_requests_by_id[sample.request_id] = sample

    return container
