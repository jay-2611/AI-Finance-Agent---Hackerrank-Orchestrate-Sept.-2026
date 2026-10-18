"""
Multi-currency conversion engine using dated exchange rates.

Converts non-home currency amounts to the user's home_currency with exact or
most recent preceding date matching, supporting direct, inverse, and triangulated rates.
Raises MissingExchangeRateError if no valid rate path exists.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

try:
    from ingest.load_data import ExchangeRate
except ImportError:
    from code.ingest.load_data import ExchangeRate


class MissingExchangeRateError(Exception):
    """Raised when no valid dated exchange rate path exists between two currencies."""
    pass


class FXConverter:
    """Dated foreign exchange converter."""

    def __init__(self, rates: Sequence[ExchangeRate]):
        self._rates = list(rates)
        # Sort rates by date ascending for efficient preceding date lookups
        self._rates.sort(key=lambda r: r.rate_date)

    def get_rate(self, from_currency: str, to_currency: str, as_of_date: date) -> Decimal:
        """
        Find the conversion rate from from_currency to to_currency on or immediately
        preceding as_of_date.
        """
        from_curr = from_currency.strip().upper()
        to_curr = to_currency.strip().upper()

        if from_curr == to_curr:
            return Decimal(1)

        # 1. Look for direct match on or before as_of_date
        direct_candidates = [
            r for r in self._rates
            if r.from_currency == from_curr
            and r.to_currency == to_curr
            and r.rate_date <= as_of_date
        ]
        if direct_candidates:
            # Pick the most recent preceding date
            best = max(direct_candidates, key=lambda r: r.rate_date)
            return best.rate

        # 2. Look for inverse match on or before as_of_date
        inverse_candidates = [
            r for r in self._rates
            if r.from_currency == to_curr
            and r.to_currency == from_curr
            and r.rate_date <= as_of_date
        ]
        if inverse_candidates:
            best = max(inverse_candidates, key=lambda r: r.rate_date)
            if best.rate == Decimal(0):
                raise MissingExchangeRateError(f"Zero rate encountered for inverse pair {to_curr}->{from_curr}")
            return Decimal(1) / best.rate

        # 3. Look for 2-hop triangulation (e.g. via USD or EUR)
        # Find all intermediate currencies that connect from_curr and to_curr
        preceding_rates = [r for r in self._rates if r.rate_date <= as_of_date]
        available_pairs = set((r.from_currency, r.to_currency) for r in preceding_rates)
        # Add inverse pairs
        for f, t in list(available_pairs):
            available_pairs.add((t, f))

        intermediates = set()
        for f, t in available_pairs:
            if f == from_curr and t != to_curr:
                intermediates.add(t)

        for inter in intermediates:
            if (inter, to_curr) in available_pairs:
                rate_1 = self.get_rate(from_curr, inter, as_of_date)
                rate_2 = self.get_rate(inter, to_curr, as_of_date)
                return rate_1 * rate_2

        # 4. If nothing before as_of_date, check if any rate exists at all (closest available)
        # But challenge specification strictly states:
        # "If exact-date rates are absent, look for the most recent preceding available date.
        # If no valid rate exists for the currency pair, raise a clear runtime error (MissingExchangeRateError). Never default to 1:1."
        raise MissingExchangeRateError(
            f"Missing exchange rate from {from_curr} to {to_curr} on or before {as_of_date}. "
            f"No valid rate exists."
        )

    def convert(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
        round_digits: Optional[int] = None,
    ) -> Decimal:
        """
        Convert an amount from from_currency to to_currency as of as_of_date.
        """
        if amount == Decimal(0):
            return Decimal(0)

        rate = self.get_rate(from_currency, to_currency, as_of_date)
        converted = amount * rate

        if round_digits is not None:
            quantum = Decimal(10) ** -round_digits
            return converted.quantize(quantum, rounding=ROUND_HALF_UP)
        return converted
