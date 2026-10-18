"""
Message intent classification and financial fact extraction engine.

Analyzes messages from employers, banks, merchants, and service providers (in English
and Indonesian) to detect cancellations, amendments, delays, and confirmations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import re
from typing import Optional

try:
    from ingest.load_data import UserMessage
except ImportError:
    from code.ingest.load_data import UserMessage


@dataclass(frozen=True)
class ExtractedMessageIntent:
    message_id: str
    user_id: str
    related_event_id: Optional[str]
    intent: str  # confirm, amend, cancel, delay, no_change
    new_amount: Optional[Decimal] = None
    currency: Optional[str] = None
    new_date: Optional[date] = None
    percentage_change: Optional[Decimal] = None
    is_unrealized_or_pending: bool = False
    is_internal_transfer: bool = False
    confidence: float = 0.95
    notes: str = ""


class MessageExtractor:
    """Extracts structured financial modifications from natural language message text."""

    @staticmethod
    def parse_message(msg: UserMessage) -> ExtractedMessageIntent:
        text = msg.message_text.strip()
        lower = text.lower()

        # 1. Internal transfer between own accounts (no net cash flow)
        if "between your two accounts" in lower or "antara dua rekening anda" in lower:
            return ExtractedMessageIntent(
                message_id=msg.message_id,
                user_id=msg.user_id,
                related_event_id=msg.related_event_id,
                intent="no_change",
                is_internal_transfer=True,
                notes="Internal account transfer with zero net effect.",
            )

        # 2. Unrealized investments or unwithdrawable / pending funds
        if (
            "market value has increased substantially" in lower
            or "no units have been sold and no cash proceeds" in lower
            or "nilai pasar yang ditampilkan telah meningkat" in lower
        ):
            return ExtractedMessageIntent(
                message_id=msg.message_id,
                user_id=msg.user_id,
                related_event_id=msg.related_event_id,
                intent="no_change",
                is_unrealized_or_pending=True,
                notes="Unrealized investment valuation; no cash generated.",
            )

        if (
            "is still pending" in lower
            or "isn't withdrawable until" in lower
            or "masih menunggu hasil akhir" in lower
            or "has not reached your account yet" in lower
            or "belum masuk ke rekening anda" in lower
            or "belum disetujui" in lower
            or "is still in payment processing" in lower
        ):
            return ExtractedMessageIntent(
                message_id=msg.message_id,
                user_id=msg.user_id,
                related_event_id=msg.related_event_id,
                intent="no_change",
                is_unrealized_or_pending=True,
                notes="Pending or unapproved funds; excluded from cash flow per rules.",
            )

        # 3. Seasonal contract ended / no future income
        if (
            "seasonal contract has ended" in lower
            or "no off-season income or renewal has been confirmed" in lower
            or "kontrak musiman saat ini telah berakhir" in lower
        ):
            return ExtractedMessageIntent(
                message_id=msg.message_id,
                user_id=msg.user_id,
                related_event_id=msg.related_event_id,
                intent="cancel",
                notes="Contract ended; recurring salary stops.",
            )

        # 4. Percentage rent increase (e.g. 12%)
        pct_match = re.search(r"increases monthly rent by (\d+)%", text, re.IGNORECASE)
        if pct_match:
            pct = Decimal(pct_match.group(1))
            return ExtractedMessageIntent(
                message_id=msg.message_id,
                user_id=msg.user_id,
                related_event_id=msg.related_event_id,
                intent="amend",
                percentage_change=pct,
                notes=f"Rent increases by {pct}%.",
            )

        # 5. Date rescheduling / delay
        date_match = re.search(r"(?:expected on|berlaku mulai|credit date is|resumes on|settlement is expected on)\s+(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
        new_date: Optional[date] = None
        if date_match:
            try:
                new_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").date()
            except ValueError:
                new_date = None

        # 6. Monetary amount extraction (e.g. IDR 42750000, EUR 1037.52, ZAR 54120, INR 196000)
        amt_match = re.search(r"(IDR|EUR|ZAR|INR|USD)\s+([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        new_amt: Optional[Decimal] = None
        curr: Optional[str] = None
        if amt_match:
            curr = amt_match.group(1).upper()
            raw_amt = amt_match.group(2).replace(",", "")
            try:
                new_amt = Decimal(raw_amt)
            except Exception:
                new_amt = None

        # Check intent based on keywords
        if (
            "replaces the payroll date" in lower
            or "revised date" in lower
            or "expected on" in lower and not new_amt
        ):
            return ExtractedMessageIntent(
                message_id=msg.message_id,
                user_id=msg.user_id,
                related_event_id=msg.related_event_id,
                intent="delay",
                new_date=new_date,
                notes="Payment date rescheduled.",
            )

        if new_amt:
            if (
                "naik menjadi" in lower
                or "reduced to" in lower
                or "temporary monthly pay is" in lower
                or "resumes on" in lower
                or "first salary will be" in lower
                or "disetujui pembayaran faktur sebesar" in lower
                or "approved an invoice payment of" in lower
                or "gaji bulanan anda" in lower
            ):
                return ExtractedMessageIntent(
                    message_id=msg.message_id,
                    user_id=msg.user_id,
                    related_event_id=msg.related_event_id,
                    intent="amend",
                    new_amount=new_amt,
                    currency=curr,
                    new_date=new_date,
                    notes=f"Amount amended to {curr} {new_amt}.",
                )

            if "sudah dikonfirmasi" in lower or "confirmed" in lower or "regular salary" in lower:
                return ExtractedMessageIntent(
                    message_id=msg.message_id,
                    user_id=msg.user_id,
                    related_event_id=msg.related_event_id,
                    intent="confirm",
                    new_amount=new_amt,
                    currency=curr,
                    new_date=new_date,
                    notes=f"Amount confirmed at {curr} {new_amt}.",
                )

        return ExtractedMessageIntent(
            message_id=msg.message_id,
            user_id=msg.user_id,
            related_event_id=msg.related_event_id,
            intent="no_change",
            notes="No explicit state modification detected.",
        )
