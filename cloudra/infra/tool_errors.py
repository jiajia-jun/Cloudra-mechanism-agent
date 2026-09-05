"""Public validation feedback, without exception dumps or implementation names."""

import re

from pydantic import ValidationError


def validation_feedback(exc: ValidationError, *, prefix: str = "arguments") -> str:
    issues = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False)[:8]:
        parts = [str(part) for part in error["loc"] if isinstance(part, int) or
                 re.fullmatch(r"[a-z_][a-z0-9_]*", str(part))]
        path = ".".join([prefix, *parts])
        kind = error["type"]
        if kind == "missing":
            hint = "required field is missing"
        elif kind == "extra_forbidden":
            hint = "field is not accepted here; use the documented nested shape"
        elif kind in {"literal_error", "enum"}:
            hint = error["msg"]
        elif kind in {"union_tag_invalid", "union_tag_not_found"}:
            hint = "missing or invalid operation/type tag; use a documented variant"
        else:
            hint = "invalid value; check the field type and constraints in the tool schema"
        issues.append(f"{path}: {hint}")
    return "Invalid tool arguments: " + "; ".join(issues)
