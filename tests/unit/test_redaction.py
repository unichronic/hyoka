from hyoka_server.services.redaction import REDACTED, redact


def test_redaction_removes_secrets_and_pii() -> None:
    payload = {
        "api_key": "sk-live",
        "message": "email ops@example.com and ssn 123-45-6789",
        "nested": {"authorization": "Bearer token"},
    }

    assert redact(payload) == {
        "api_key": REDACTED,
        "message": f"email {REDACTED} and ssn {REDACTED}",
        "nested": {"authorization": REDACTED},
    }

