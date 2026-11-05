# ADR 0002: Opaque, hashed OAuth2 tokens instead of JWT

Status: accepted (2026-11-05)

## Context

The Foundation API lets the server choose the token format ("an arbitrary
string"). The prototype used HS256 JWTs with a custom `expires` claim that was
never checked, stored them in clear text and could not revoke them. RFC 9700
(OAuth 2.0 Security Best Current Practice) requires refresh token rotation
with reuse detection for public clients, which needs server-side state anyway.

## Decision

Access tokens, refresh tokens and authorization codes are random strings of
256 bits (`secrets.token_urlsafe(32)`). The server stores only their SHA-256
hash together with the owner, client, scope, `expires_at` and, for refresh
tokens, a `family_id`. Validation is a lookup; revocation is a delete. Refresh
tokens rotate on every use; reuse revokes the whole family.

## Consequences

- No signing keys to manage or rotate, no algorithm confusion, no clock skew
  disputes with clients.
- Every API call costs one indexed lookup. Acceptable at this scale; a cache
  can be added later without changing the token format.
- Tokens cannot be validated by a third party without asking the server. If an
  external resource server ever needs that, add RFC 7662 introspection.
