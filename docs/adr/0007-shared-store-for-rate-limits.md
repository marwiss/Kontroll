# ADR 0007: An optional shared store for the rate limits

Status: accepted (2026-11-06)

## Context

The counts behind the rate limits live in the server process. One process is what
the images run, and it is enough for most servers. Several processes behind a
proxy each count on their own, so the limit is multiplied by their number.

## Decision

`OPENCDE_RATE_LIMIT_STORAGE` names the store, `memory://` by default. A
`redis://` address uses the `redis` package, which is an optional extra of the
project and not part of the default image: most operators need neither the
dependency nor a second service. A store that fails while the server runs lets
requests through and logs a warning, since an availability problem in a limiter
must not take the server down; a store that stops answering holds a request for
at most a second, and an address that cannot work at all stops the start. The
address is treated as a secret, since it can hold a password.

The limit on every request is checked in a middleware that talks to `limits`
directly, which comes with `slowapi`, so `limits` is now a declared dependency.

The wait after failed sign-ins is not affected: it lives in the graph and is
shared by every process anyway.

## Consequences

The `redis` package is a new, optional dependency, and part of the development
group so that a test can run against a real store. An operator who runs several
processes builds the image with the extra and runs Redis. Nothing changes for
anyone else.
