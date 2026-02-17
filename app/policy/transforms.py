from copy import deepcopy
from typing import Any

from app.policy.models import TransformAction


def apply_transforms(payload: dict[str, Any], transforms: list[TransformAction]) -> dict[str, Any]:
    output = deepcopy(payload)

    for transform in transforms:
        if transform.type == "set_max_tokens":
            value = int(transform.args.get("value", output.get("max_tokens", 256)))
            output["max_tokens"] = value
        elif transform.type == "override_model":
            model = str(transform.args.get("model", output.get("model", "")))
            output["model"] = model
        elif transform.type == "prepend_system_guardrail":
            text = str(transform.args.get("text", ""))
            if not text:
                continue
            messages = list(output.get("messages", []))
            messages.insert(0, {"role": "system", "content": text})
            output["messages"] = messages

    return output
