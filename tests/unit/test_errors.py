from app.core.errors import ErrorEnvelope


def test_error_envelope_shape() -> None:
    envelope = ErrorEnvelope(
        code="auth_invalid",
        message="Invalid API key",
        type="auth",
        request_id="req-1",
    )
    payload = envelope.as_dict()
    assert payload == {
        "error": {
            "code": "auth_invalid",
            "message": "Invalid API key",
            "type": "auth",
            "request_id": "req-1",
        }
    }
