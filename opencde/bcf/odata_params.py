# This file was generated with the assistance of an AI coding tool.
"""The ``$filter``, ``$orderby``, ``$top`` and ``$skip`` query parameters as a FastAPI dependency.

A list that the server cuts at its own limit, because the caller gave no ``$top`` or a larger one, says so: the
answer gets ``X-Total-Count`` with the number of matches and ``Link: <…>; rel="next"`` with the address of the rest
(F14 a, S-13). Both are additions of this server; BCF names neither.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, Response

from opencde.odata import Compiled, Field, ODataError, compile_odata

MAX_TOP = 1000  # the longest list the server gives at once


@dataclass(frozen=True)
class ODataParams:
    filter: str | None
    orderby: str | None
    top: int | None
    skip: int | None
    request: Request | None = None
    response: Response | None = None

    def compile(
        self,
        fields: Mapping[str, Field],
        orderable: Iterable[str],
        default_order: str,
        default_sql_order: str | None = None,
    ) -> Compiled:
        try:
            return compile_odata(
                filter_=self.filter,
                orderby=self.orderby,
                top=self.top,
                skip=self.skip,
                fields=fields,
                orderable=orderable,
                default_order=default_order,
                max_top=MAX_TOP,
                default_sql_order=default_sql_order,
            )
        except ODataError as exc:
            raise HTTPException(400, f"Invalid query options: {exc}") from None

    async def say_if_cut(self, compiled: Compiled, returned: int, count: Callable[[], Awaitable[int]]) -> None:
        """``X-Total-Count`` and ``Link: rel="next"`` on a list the server's limit cut; nothing on a whole list."""
        if not compiled.capped or returned < compiled.limit or self.request is None or self.response is None:
            return
        total = await count()
        if total <= compiled.skip + returned:
            return
        following = self.request.url.include_query_params(**{"$skip": str(compiled.skip + returned)})
        self.response.headers["X-Total-Count"] = str(total)
        self.response.headers["Link"] = f'<{following}>; rel="next"'


def odata_params(
    request: Request,
    response: Response,
    filter: Annotated[str | None, Query(alias="$filter", max_length=2000)] = None,
    orderby: Annotated[str | None, Query(alias="$orderby", max_length=200)] = None,
    top: Annotated[int | None, Query(alias="$top", ge=0, le=1_000_000)] = None,
    skip: Annotated[int | None, Query(alias="$skip", ge=0, le=1_000_000)] = None,
) -> ODataParams:
    return ODataParams(filter=filter, orderby=orderby, top=top, skip=skip, request=request, response=response)


ODataDep = Annotated[ODataParams, Depends(odata_params)]
