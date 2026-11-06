# This file was generated with the assistance of an AI coding tool.
"""What the request and response bodies of the APIs have in common."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class ApiModel(BaseModel):
    # Strict: the schemas say boolean and integer, so "yes" and "5" are refused rather than taken kindly.
    # Unknown fields are ignored (Foundation API 1.8).
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, strict=True)

    @model_validator(mode="before")
    @classmethod
    def _lengths_of_what_was_sent(cls, data: Any) -> Any:
        """The API document's maxLength is about what is sent, but stripping whitespace comes before the field's check."""
        if isinstance(data, dict):
            for name, field in cls.model_fields.items():
                value = data.get(field.alias or name)
                if isinstance(value, str):
                    for rule in field.metadata:
                        limit = getattr(rule, "max_length", None)
                        if limit is not None and len(value) > limit:
                            raise ValueError(f"{name} must have at most {limit} characters")
        return data
