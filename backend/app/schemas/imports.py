"""Schemas for master data import endpoints."""

from pydantic import BaseModel

from app.schemas.clients import EmployeeOut


class ImportEmployeeResult(BaseModel):
    total_rows: int
    created: int
    updated: int
    skipped: int
    errors: list[str]
    employees: list[EmployeeOut]


class ImportPayrollResult(BaseModel):
    period: str
    total_rows: int
    matched: int
    unmatched: int
    created_entries: int
    errors: list[str]
