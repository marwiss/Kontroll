# This file was generated with the assistance of an AI coding tool.
import logging

from opencde.logging import REDACTED, configure_logging, redact_secrets


def test_driver_logger_never_goes_below_info() -> None:
    configure_logging("DEBUG", json_output=False)
    assert logging.getLogger("neo4j").level == logging.INFO
    configure_logging("WARNING", json_output=False)
    assert logging.getLogger("neo4j").level == logging.WARNING


def test_credential_keys_are_redacted_at_any_depth() -> None:
    event = {
        "event": "token_issued",
        "access_token": "abc",
        "client": {"client_secret": "xyz", "name": "openBCF"},
        "headers": [{"Authorization": "Bearer abc"}],
        "user": "officer",
    }
    redacted = redact_secrets(None, "info", event)
    assert redacted["access_token"] == REDACTED
    assert redacted["client"]["client_secret"] == REDACTED
    assert redacted["client"]["name"] == "openBCF"
    assert redacted["headers"][0]["Authorization"] == REDACTED
    assert redacted["user"] == "officer"


def test_fragment_rule_catches_new_names() -> None:
    event = {"refresh_token_hash": "h", "db_password": "p", "Set-Cookie": "s", "code": "c", "count": 3, "state": "ok"}
    redacted = redact_secrets(None, "info", event)
    assert redacted["refresh_token_hash"] == REDACTED
    assert redacted["db_password"] == REDACTED
    assert redacted["Set-Cookie"] == REDACTED
    assert redacted["code"] == REDACTED
    assert redacted["count"] == 3
    assert redacted["state"] == "ok"  # OAuth2 state is not a secret and is useful in logs
