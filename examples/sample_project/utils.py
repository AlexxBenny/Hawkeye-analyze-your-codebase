"""Utility functions — no internal dependencies."""


def format_currency(amount: float) -> str:
    return f"${amount:,.2f}"


def slugify(text: str) -> str:
    return text.lower().replace(" ", "-")
