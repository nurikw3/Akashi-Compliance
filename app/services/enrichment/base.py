from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field


class CompanyData(BaseModel):
    iin: str
    name: Optional[str] = None
    status: Optional[str] = None
    tax_debt: Optional[float] = None
    court_cases: Optional[int] = None
    in_sanctions_list: Optional[bool] = None
    director: Optional[str] = None
    address: Optional[str] = None
    registration_date: Optional[str] = None
    employees: Optional[int] = None
    industry: Optional[str] = None
    founders: list[dict[str, Any]] = Field(default_factory=list)
    related_companies: list[dict[str, Any]] = Field(default_factory=list)
    court_cases_years: list[dict[str, Any]] = Field(default_factory=list)
    court_totals: dict[str, int] = Field(default_factory=dict)
    status_flags: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    tax_payments_total: Optional[float] = None
    tax_payments_yearly: list[dict[str, Any]] = Field(default_factory=list)
    contacts: dict[str, Any] = Field(default_factory=dict)
    requisites: dict[str, Any] = Field(default_factory=dict)
    section_sources: dict[str, str] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class BaseProvider(ABC):
    name: str

    @abstractmethod
    async def check(self, iin: str) -> CompanyData | None:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...
