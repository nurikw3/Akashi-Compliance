from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

DuplicatePolicy = Literal["create", "skip", "refresh"]


class AuditRunRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)
    bin: str = Field(min_length=1, max_length=32)

    @field_validator("organization_name", "bin")
    @classmethod
    def strip_string(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field must not be empty.")
        return cleaned


class AuditHistoryItem(BaseModel):
    id: int
    checked_at: str
    organization_name: str
    bin: str
    status: str
    pdf_path: str | None = None
    pdf_ready: bool = False


class AuditDetail(BaseModel):
    id: int
    audit_hash: str
    checked_at: str
    organization_name: str
    bin: str
    status: str
    from_cache: bool
    raw_result: dict[str, Any]
    pdf_path: str | None = None
    pdf_ready: bool = False


class UploadCaseItem(BaseModel):
    name: str = Field(min_length=1)
    iinBin: str = Field(min_length=1)

    @field_validator("name", "iinBin")
    @classmethod
    def strip_value(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field must not be empty.")
        return cleaned


class UploadCasesRequest(BaseModel):
    cases: list[UploadCaseItem]
    onDuplicate: DuplicatePolicy = "create"


class ParseBinsRequest(BaseModel):
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field must not be empty.")
        return cleaned


class CheckDuplicatesRequest(BaseModel):
    iinBins: list[str] = Field(min_length=1)

    @field_validator("iinBins")
    @classmethod
    def strip_bins(cls, value: list[str]) -> list[str]:
        return [v.strip() for v in value if v and v.strip()]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message must not be empty.")
        return cleaned


class DocumentRequest(BaseModel):
    filename: str = Field(min_length=1)
    fileType: str = Field(min_length=1)
    analysis: str | None = None


class LookupRequest(BaseModel):
    name: str = Field(min_length=1)
    iinBin: str = Field(min_length=1)
    sync: bool = False
    parentCaseId: str | None = None

    @field_validator("name", "iinBin")
    @classmethod
    def strip_fields(cls, value: str) -> str:
        return value.strip()
