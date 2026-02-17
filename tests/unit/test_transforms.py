from app.policy.models import TransformAction
from app.policy.transforms import apply_transforms


def test_apply_transforms_sequence() -> None:
    payload = {
        "model": "gpt-4o-mini",
        "max_tokens": 128,
        "messages": [{"role": "user", "content": "hello"}],
    }
    transforms = [
        TransformAction(type="set_max_tokens", args={"value": 42}),
        TransformAction(type="override_model", args={"model": "gpt-4o"}),
        TransformAction(type="prepend_system_guardrail", args={"text": "guardrail"}),
    ]

    output = apply_transforms(payload, transforms)

    assert output["max_tokens"] == 42
    assert output["model"] == "gpt-4o"
    assert output["messages"][0]["role"] == "system"
