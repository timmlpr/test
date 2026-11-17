from __future__ import annotations

from fastapi import HTTPException


class ApiError(HTTPException):
    """Error with a stable machine code; the frontend maps codes to plain-language i18n text."""

    def __init__(self, status: int, code: str, detail: str | None = None, **extra):
        super().__init__(status_code=status, detail={"code": code, "message": detail or code, **extra})
