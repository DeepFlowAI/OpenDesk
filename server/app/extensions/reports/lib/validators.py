"""Shared validators for reports endpoints."""
from datetime import date

from fastapi import HTTPException, status


def validate_date_range(start_date: date, end_date: date, max_days: int = 366) -> None:
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date cannot be later than end date",
        )
    if (end_date - start_date).days + 1 > max_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You can query up to {max_days} days",
        )
