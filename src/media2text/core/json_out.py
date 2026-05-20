import json
import sys
from typing import Any


def emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(payload.get("message", json.dumps(payload, ensure_ascii=False)) + "\n")
