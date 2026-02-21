"""
Pydantic models for BlackRock Auto-Savings API.
All date strings are parsed to datetime ONCE here -- never inside loops.
All output doubles are rounded to 2 decimal places.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, GetJsonSchemaHandler, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema as _pcs

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _parse_date(v: object) -> datetime:
    """Parse a date string in 'YYYY-MM-DD HH:mm:ss' format to datetime."""
    if isinstance(v, datetime):
        return v
    if not isinstance(v, str):
        raise ValueError("Invalid date format. Expected: YYYY-MM-DD HH:mm:ss")
    try:
        return datetime.strptime(v, DATE_FORMAT)
    except ValueError:
        raise ValueError("Invalid date format. Expected: YYYY-MM-DD HH:mm:ss")


class _DateTimeFieldType:
    """
    Custom Pydantic type that:
      - At runtime: validates and stores a datetime (via _parse_date)
      - In OpenAPI/Swagger: shows as a plain string with the correct example
        so Swagger UI does NOT render an ISO 8601 datetime picker.
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        return _pcs.no_info_plain_validator_function(
            _parse_date,
            serialization=_pcs.plain_serializer_function_ser_schema(
                lambda v: v.strftime(DATE_FORMAT) if isinstance(v, datetime) else str(v),
                info_arg=False,
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: Any, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {
            "type": "string",
            "example": "2023-10-12 20:15:30",
            "description": "Format: YYYY-MM-DD HH:mm:ss",
        }


# Use this instead of bare `datetime` for all input date fields.
# Swagger will show a plain string input with the correct example format.
DateTimeField = _DateTimeFieldType


def _fmt_date(dt: datetime) -> str:
    return dt.strftime(DATE_FORMAT)


def _round2(v: float) -> float:
    return round(float(v), 2)


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class Expense(BaseModel):
    """Raw expense -- input to EP1, EP3, EP4."""
    date: DateTimeField
    amount: float

    @field_validator("amount", mode="before")
    @classmethod
    def check_amount(cls, v: object) -> float:
        if v is None:
            raise ValueError("Amount is required")
        return float(v)


class Transaction(BaseModel):
    """Parsed transaction -- output of EP1, input to EP2."""
    date: DateTimeField
    amount: float
    ceiling: float
    remanent: float

    @field_validator("amount", "ceiling", "remanent", mode="before")
    @classmethod
    def check_numeric(cls, v: object) -> float:
        if v is None:
            raise ValueError("Amount is required")
        return float(v)


class QPeriod(BaseModel):
    fixed: float
    start: DateTimeField
    end: DateTimeField

    @field_validator("fixed", mode="before")
    @classmethod
    def check_fixed(cls, v: object) -> float:
        val = float(v)
        if val < 0:
            raise ValueError("q period fixed value must be non-negative")
        return val

    @model_validator(mode="after")
    def check_order(self) -> "QPeriod":
        if self.start > self.end:
            raise ValueError("Invalid q period: start must be before end")
        return self


class PPeriod(BaseModel):
    extra: float
    start: DateTimeField
    end: DateTimeField

    @field_validator("extra", mode="before")
    @classmethod
    def check_extra(cls, v: object) -> float:
        val = float(v)
        if val < 0:
            raise ValueError("p period extra value must be non-negative")
        return val

    @model_validator(mode="after")
    def check_order(self) -> "PPeriod":
        if self.start > self.end:
            raise ValueError("Invalid p period: start must be before end")
        return self


class KPeriod(BaseModel):
    start: DateTimeField
    end: DateTimeField

    @model_validator(mode="after")
    def check_order(self) -> "KPeriod":
        if self.start > self.end:
            raise ValueError("Invalid k period: start must be before end")
        return self


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class ValidatorRequest(BaseModel):
    wage: Optional[float] = Field(default=None, validate_default=True)
    transactions: Optional[List[Transaction]] = Field(default=None, validate_default=True)

    @field_validator("wage", mode="before")
    @classmethod
    def check_wage(cls, v: object) -> float:
        if v is None:
            raise ValueError("Wage is required")
        val = float(v)
        if val <= 0:
            raise ValueError("Wage must be a positive number")
        return val

    @field_validator("transactions", mode="before")
    @classmethod
    def check_txns(cls, v: object) -> object:
        if v is None:
            raise ValueError("Transactions list is required")
        return v


class FilterRequest(BaseModel):
    wage: Optional[float] = Field(default=None, validate_default=True)
    transactions: List[Expense]
    q: List[QPeriod] = []
    p: List[PPeriod] = []
    k: List[KPeriod] = []

    @field_validator("wage", mode="before")
    @classmethod
    def check_wage(cls, v: object) -> float:
        if v is None:
            raise ValueError("Wage is required")
        val = float(v)
        if val <= 0:
            raise ValueError("Wage must be a positive number")
        return val


class ReturnsRequest(BaseModel):
    age: Optional[int] = Field(default=None, validate_default=True)
    wage: Optional[float] = Field(default=None, validate_default=True)
    inflation: Optional[float] = Field(default=None, validate_default=True)
    transactions: List[Expense]
    q: List[QPeriod] = []
    p: List[PPeriod] = []
    k: Optional[List[KPeriod]] = Field(default=None, validate_default=True)

    @field_validator("age", mode="before")
    @classmethod
    def check_age(cls, v: object) -> int:
        if v is None:
            raise ValueError("Age is required and must be a whole number")
        if not isinstance(v, int) or isinstance(v, bool):
            # allow int-valued floats
            if isinstance(v, float) and v == int(v):
                v = int(v)
            else:
                raise ValueError("Age is required and must be a whole number")
        val = int(v)
        if val <= 0:
            raise ValueError("Age must be a positive number")
        return val

    @field_validator("wage", mode="before")
    @classmethod
    def check_wage(cls, v: object) -> float:
        if v is None:
            raise ValueError("Wage is required")
        val = float(v)
        if val <= 0:
            raise ValueError("Wage must be a positive number")
        return val

    @field_validator("inflation", mode="before")
    @classmethod
    def check_inflation(cls, v: object) -> float:
        if v is None:
            raise ValueError("Inflation rate is required")
        val = float(v)
        if val < 0:
            raise ValueError("Inflation rate must be non-negative")
        return val

    @field_validator("k", mode="before")
    @classmethod
    def check_k(cls, v: object) -> object:
        if not v:
            raise ValueError("At least one k period is required")
        return v


# ---------------------------------------------------------------------------
# Response / output models
# ---------------------------------------------------------------------------

class TransactionOut(BaseModel):
    date: str
    amount: float
    ceiling: float
    remanent: float

    @classmethod
    def from_txn(cls, t: "TransactionData") -> "TransactionOut":
        return cls(
            date=_fmt_date(t.date),
            amount=_round2(t.amount),
            ceiling=_round2(t.ceiling),
            remanent=_round2(t.remanent),
        )


class FilteredTransactionOut(BaseModel):
    date: str
    amount: float
    ceiling: float
    remanent: float
    inkPeriod: bool

    @classmethod
    def from_txn(cls, t: "TransactionData") -> "FilteredTransactionOut":
        return cls(
            date=_fmt_date(t.date),
            amount=_round2(t.amount),
            ceiling=_round2(t.ceiling),
            remanent=_round2(t.remanent),
            inkPeriod=getattr(t, "inkPeriod", False),
        )


class InvalidTransactionOut(BaseModel):
    date: str
    amount: float
    message: str
    ceiling: Optional[float] = None
    remanent: Optional[float] = None

    @classmethod
    def from_ep2(cls, t: "TransactionData", message: str) -> "InvalidTransactionOut":
        return cls(
            date=_fmt_date(t.date),
            amount=_round2(t.amount),
            ceiling=_round2(t.ceiling),
            remanent=_round2(t.remanent),
            message=message,
        )

    @classmethod
    def from_ep3(cls, t: "TransactionData", message: str) -> "InvalidTransactionOut":
        return cls(
            date=_fmt_date(t.date),
            amount=_round2(t.amount),
            message=message,
        )


class ValidatorResponse(BaseModel):
    valid: List[TransactionOut]
    invalid: List[InvalidTransactionOut]


class FilterResponse(BaseModel):
    valid: List[FilteredTransactionOut]
    invalid: List[InvalidTransactionOut]


class SavingResult(BaseModel):
    start: str
    end: str
    amount: float
    profit: float
    taxBenefit: float


class ReturnsResponse(BaseModel):
    totalTransactionAmount: float
    totalCeiling: float
    savingsByDates: List[SavingResult]


class PerformanceResponse(BaseModel):
    time: str
    memory: str
    threads: int


# ---------------------------------------------------------------------------
# Internal data containers (not Pydantic, for speed inside pipeline)
# ---------------------------------------------------------------------------

class TransactionData:
    """Lightweight mutable container used inside the processing pipeline."""

    __slots__ = ("date", "amount", "ceiling", "remanent", "inkPeriod")

    def __init__(
        self,
        date: datetime,
        amount: float,
        ceiling: float = 0.0,
        remanent: float = 0.0,
        inkPeriod: bool = False,
    ) -> None:
        self.date = date
        self.amount = amount
        self.ceiling = ceiling
        self.remanent = remanent
        self.inkPeriod = inkPeriod
