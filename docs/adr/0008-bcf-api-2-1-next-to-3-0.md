# ADR 0008: BCF API 2.1 next to 3.0

Status: accepted (2026-11-06)

## Context

The server implemented BCF API 3.0 and answered 404 under `/bcf/2.1/`. Clients and servers that speak only 2.1 exist,
and the owner decided that a client that implements only 2.1 must be able to connect. Which versions a server has is
told by the Foundation API's `GET /foundation/versions`, but a client of 2.1 knows nothing of the Foundation API, so
it also has to find them at `GET /bcf/versions`.

2.1 is close to 3.0, but no subset of it. Thirty-eight of its forty-one services have the same address. It has its own
versions, authentication and user services, which 3.0 moved to the Foundation API, and a few fields under other names.
Its OAuth2 example does not know PKCE, which this server has required of every client.

BCF API 1.0 was left out: 25 of its 59 services are shared with 3.0, its viewpoints have another shape, and it has
services that conflict with this server's data model, such as creating projects and changing viewpoints.

## Decision

Both versions run on the same data, under their own addresses. `/foundation/versions` and `/bcf/versions` list them
with the newest first, so a client that takes the first entry for its API goes on getting 3.0.

A route of 3.0 that answers 2.1's request as it stands is mounted a second time. Every other route of 2.1 is a thin
layer that calls the route of 3.0 and turns the answer into what 2.1 says, so the checks of who may do what are in one
place, and the versions cannot come to disagree about permissions. Each version's answers hold what its specification
says and nothing of the other's, so a client tested here does not come to lean on fields other servers lack.

What 2.1 has and 3.0 does not, replies between comments, is stored, and 3.0 neither shows nor changes it. What 3.0
requires and 2.1 does not have, a camera's aspect ratio, gets a neutral value of 1.0 when a viewpoint is made through
2.1, so that it can be read through 3.0.

PKCE remains required, except for a confidential client marked `pkce_optional`, which an administrator sets, or which
comes with registering at 2.1's own registration address when dynamic registration is on. RFC 9700 section 2.1.1
requires PKCE of public clients and recommends it for confidential ones. Without it, the client's secret is what
makes a stolen code worthless. The rest of section 2.1.1 still holds: a challenge that is sent is enforced, a verifier
for a code without a challenge is refused, and the redirect URI named in a request must be named again (RFC 6749
section 4.1.3). The audit log says when PKCE was left out.

## Consequences

The API document and the tests that walk it have some forty more operations. Every change to the BCF API has to hold
for both versions. The contribution to IfcOpenShell becomes larger to review; `routes_v21.py` and `schemas_v21.py`
can be left out of it without touching anything else, though the marked clients and the replies would then have no
use.

A client that registers at the Foundation API's address, or that an administrator has not marked, is treated as before.
No client changes behaviour by this, except that one which takes the last `bcf` entry of the versions service gets 2.1.
