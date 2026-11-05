# This file was generated with the assistance of an AI coding tool.
import time

import pytest

from opencde.auth import pkce
from opencde.auth.forms import FormTokenError, FormTokens
from opencde.auth.scopes import ScopeError, parse_scope, scope_string


def test_pkce_matches_rfc_7636_appendix_b_vector() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert pkce.challenge_for(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert pkce.verify(verifier, "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
    assert not pkce.verify(verifier, "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cN")
    assert not pkce.verify("too-short", pkce.challenge_for("too-short"))
    assert not pkce.verify(None, None)
    assert not pkce.is_valid_challenge("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM=")  # padding is not allowed
    assert not pkce.is_valid_challenge("short")


def test_form_tokens_round_trip_and_rejections() -> None:
    tokens = FormTokens("k" * 40, max_age_seconds=60)
    signed = tokens.sign("login", {"client_id": "c1", "state": "s"})
    assert tokens.load(signed, "login") == {"client_id": "c1", "state": "s"}
    with pytest.raises(FormTokenError, match="purpose"):
        tokens.load(signed, "other")
    with pytest.raises(FormTokenError):
        tokens.load(signed[:-3] + "xyz", "login")
    with pytest.raises(FormTokenError):
        tokens.load(None, "login")
    with pytest.raises(FormTokenError):
        FormTokens("other-key-" * 4, max_age_seconds=60).load(signed, "login")
    expired = FormTokens("k" * 40, max_age_seconds=0)
    stale = expired.sign("login", {})
    time.sleep(1.1)
    with pytest.raises(FormTokenError):
        expired.load(stale, "login")


def test_scopes() -> None:
    assert parse_scope(None) == ["profile", "bcf", "documents"]
    assert parse_scope("bcf bcf profile") == ["bcf", "profile"]
    assert scope_string(["bcf", "documents"]) == "bcf documents"
    assert parse_scope("profile admin") == ["profile", "admin"], "admin exists but is never granted by default"
    assert "admin" not in parse_scope(None)
    with pytest.raises(ScopeError):
        parse_scope("superuser")
