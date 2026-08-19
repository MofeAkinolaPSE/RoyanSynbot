"""Convert a Naira amount to words for printed invoices (e.g. "Two Hundred
Fifty Five Thousand Three Hundred Fourteen Naira Only"), matching the format
shown on the legacy Hope invoice template. Self-contained — no dependency,
since a single-purpose helper like this doesn't warrant one.
"""
from __future__ import annotations

_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety",
]
_SCALES = [(1_000_000_000, "Billion"), (1_000_000, "Million"), (1_000, "Thousand"), (100, "Hundred")]


def _int_to_words(n: int) -> str:
    if n == 0:
        return "Zero"
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, rem = divmod(n, 10)
        return _TENS[tens] + (f" {_ONES[rem]}" if rem else "")

    parts: list[str] = []
    remaining = n
    for scale_value, scale_name in _SCALES:
        if remaining >= scale_value:
            count, remaining = divmod(remaining, scale_value)
            parts.append(f"{_int_to_words(count)} {scale_name}")
    if remaining:
        parts.append(_int_to_words(remaining))
    return " ".join(parts)


def naira_in_words(amount: float) -> str:
    """Render a currency amount as words, e.g. 255314.00 -> 'Two Hundred
    Fifty Five Thousand Three Hundred Fourteen Naira Only'. Kobo is included
    only when the amount has a fractional part."""
    amount = round(abs(float(amount)), 2)
    naira = int(amount)
    kobo = round((amount - naira) * 100)

    words = f"{_int_to_words(naira)} Naira"
    if kobo:
        words += f" {_int_to_words(kobo)} Kobo"
    return f"{words} Only"
