"""Financial periods of RMS: the financial year runs from July to June."""

from datetime import date

QUARTERS = ("Q1 · Jul–Sep", "Q2 · Oct–Dec", "Q3 · Jan–Mar", "Q4 · Apr–Jun")  # noqa: RUF001


def fiscal_year_start(day: date) -> int:
    """Calendar year in which the financial year of `day` starts (July)."""
    return day.year if day.month >= 7 else day.year - 1


def fiscal_year(day: date) -> str:
    """ "FY2025/26" for any day from 1 July 2025 to 30 June 2026."""
    start = fiscal_year_start(day)
    return f"FY{start}/{(start + 1) % 100:02d}"


def fiscal_quarter(month: int) -> str:
    """Quarter of the financial year of a calendar month (July = Q1)."""
    return QUARTERS[((month - 7) % 12) // 3]
