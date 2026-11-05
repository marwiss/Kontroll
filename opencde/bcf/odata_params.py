# This file was generated with the assistance of an AI coding tool.
"""The ``$filter``, ``$orderby``, ``$top`` and ``$skip`` query parameters as a FastAPI dependency."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Annotated

from fastapi import HTTPException, Query

from opencde.odata import Compiled, Field, ODataError, compile_odata


@dataclass(frozen=True)
class ODataParams:
    filter: str | None
    orderby: str | None
    top: int | None
    skip: int | None

    def compile(self, fields: Mapping[str, Field], orderable: Iterable[str], default_order: str) -> Compiled:
        try:
            return compile_odata(
                filter_=self.filter,
                orderby=self.orderby,
                top=self.top,
                skip=self.skip,
                fields=fields,
                orderable=orderable,
                default_order=default_order,
            )
        except ODataError as exc:
            raise HTTPException(400, f"Invalid query options: {exc}") from None


def odata_params(
    filter: Annotated[str | None, Query(alias="$filter", max_length=2000)] = None,
    orderby: Annotated[str | None, Query(alias="$orderby", max_length=200)] = None,
    top: Annotated[int | None, Query(alias="$top", ge=0, le=1_000_000)] = None,
    skip: Annotated[int | None, Query(alias="$skip", ge=0, le=1_000_000)] = None,
) -> ODataParams:
    return ODataParams(filter=filter, orderby=orderby, top=top, skip=skip)
