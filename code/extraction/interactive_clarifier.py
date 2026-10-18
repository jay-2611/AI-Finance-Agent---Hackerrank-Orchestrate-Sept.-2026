"""
Interactive Ambiguity Clarification Layer (Section 10.1).

Confidence-gated protocol triggering human-in-the-loop clarification when model
extraction confidence drops below 90%. Emits structured 3-part clarification schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import sys
from typing import Optional


@dataclass(frozen=True)
class ClarificationRequest:
    detected_issue: str
    best_guess_assumption: str
    direct_interactive_prompt: str


@dataclass(frozen=True)
class ClarificationResult:
    committed_amount: Decimal
    source: str  # 'user_confirmed', 'user_override', 'autonomous_best_guess'
    was_clarified: bool


class InteractiveClarifier:
    """Confidence-gated ambiguity resolver."""

    CONFIDENCE_THRESHOLD = 0.90

    def __init__(self, interactive_mode: bool = False):
        self.interactive_mode = interactive_mode

    def evaluate_and_clarify(
        self,
        event_id: str,
        best_guess_amount: Decimal,
        currency: str,
        confidence: float,
        issue_description: str,
    ) -> ClarificationResult:
        """
        Evaluate confidence score. If < 0.90, prompt user or use verified fallback.
        """
        if confidence >= self.CONFIDENCE_THRESHOLD:
            return ClarificationResult(
                committed_amount=best_guess_amount,
                source="high_confidence_auto",
                was_clarified=False,
            )

        req = ClarificationRequest(
            detected_issue=f"Low confidence ({confidence*100:.1f}%) for {event_id}: {issue_description}",
            best_guess_assumption=f"Best guess: {currency} {best_guess_amount:,.2f}",
            direct_interactive_prompt=f"Please reply 'Yes' to confirm {currency} {best_guess_amount:,.2f} or enter the exact amount:",
        )

        if self.interactive_mode and sys.stdin.isatty():
            print("\n[CLARIFICATION REQUIRED]")
            print(f"1. Detected Issue: {req.detected_issue}")
            print(f"2. Best Guess: {req.best_guess_assumption}")
            user_input = input(f"3. {req.direct_interactive_prompt} ").strip()

            if user_input.lower() in {"yes", "y", ""}:
                return ClarificationResult(
                    committed_amount=best_guess_amount,
                    source="user_confirmed",
                    was_clarified=True,
                )
            else:
                try:
                    cleaned = user_input.replace(",", "").replace(currency, "").strip()
                    val = Decimal(cleaned)
                    return ClarificationResult(
                        committed_amount=val,
                        source="user_override",
                        was_clarified=True,
                    )
                except Exception:
                    print(f"Could not parse '{user_input}', defaulting to best guess.")

        return ClarificationResult(
            committed_amount=best_guess_amount,
            source="autonomous_best_guess",
            was_clarified=False,
        )
