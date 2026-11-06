# This file was generated with the assistance of an AI coding tool.
"""A growing wait after failed sign-ins, per user name, on top of the rate limit per address.

Someone with many addresses gets past the limit per address, so failures are also counted per user name, in
the graph, where every server process sees them. The first attempts cost nothing; after that each failure
doubles the wait, up to a ceiling. Unknown names count the same way, so the answer says nothing about which
accounts exist, and names are stored only as hashes.

The price of counting per name is that anyone can make an account wait by failing on purpose. The ceiling is
what keeps that a nuisance rather than a lockout, and nothing here ever disables an account.
"""

from __future__ import annotations

from opencde.accounts.users import User, UserRepository
from opencde.graph.graph import Graph, Tx
from opencde.ids import hash_secret
from opencde.settings import Settings
from opencde.timeutil import later_iso, now_iso, parse_iso

FORGET_AFTER_SECONDS = 24 * 3600


class SignInThrottled(Exception):
    """The user name has to wait before the next attempt."""

    def __init__(self, seconds: int) -> None:
        super().__init__(f"wait {seconds} seconds")
        self.seconds = seconds


def _key(username: str) -> str:
    return hash_secret(username.strip().casefold())


def delay_after(failures: int, settings: Settings) -> int:
    """Seconds to wait after this many failures in a row: none at first, then doubling up to the ceiling."""
    over = failures - settings.sign_in_free_attempts
    if over < 0:
        return 0
    # The exponent is capped so that a very long run of failures cannot grow the number without end.
    return min(settings.sign_in_delay_seconds * 2 ** min(over, 30), settings.sign_in_max_delay_seconds)


async def wait_seconds(graph: Graph, username: str) -> int:
    """How long this user name still has to wait; 0 when it may try."""
    row = await graph.one("MATCH (t:SignInThrottle {key: $key}) RETURN t.blocked_until AS until", key=_key(username))
    until = row["until"] if row else None
    if not until:
        return 0
    remaining = (parse_iso(until) - parse_iso(now_iso())).total_seconds()
    return max(0, int(remaining) + 1) if remaining > 0 else 0


async def record_failure(graph: Graph, username: str, settings: Settings) -> None:
    key = _key(username)

    async def work(tx: Tx) -> None:
        row = await tx.one(
            """
            MERGE (t:SignInThrottle {key: $key})
            SET t.failures = coalesce(t.failures, 0) + 1, t.expires_at = $expires
            RETURN t.failures AS failures
            """,
            key=key,
            expires=later_iso(FORGET_AFTER_SECONDS),
        )
        delay = delay_after(row["failures"] if row else 1, settings)
        if delay:
            await tx.run(
                "MATCH (t:SignInThrottle {key: $key}) SET t.blocked_until = $until", key=key, until=later_iso(delay)
            )

    await graph.write(work)


async def forget(graph: Graph, username: str) -> None:
    await graph.run("MATCH (t:SignInThrottle {key: $key}) DETACH DELETE t", key=_key(username))


async def authenticate(
    users: UserRepository, graph: Graph, settings: Settings, username: str, password: str
) -> User | None:
    """``users.authenticate`` behind the wait. Raises :class:`SignInThrottled` without looking at the password."""
    if not settings.sign_in_throttle_enabled:
        return await users.authenticate(username, password)
    seconds = await wait_seconds(graph, username)
    if seconds:
        raise SignInThrottled(seconds)
    user = await users.authenticate(username, password)
    if user is None:
        await record_failure(graph, username, settings)
    else:
        await forget(graph, username)
    return user


__all__ = ["SignInThrottled", "authenticate", "delay_after", "forget", "record_failure", "wait_seconds"]
