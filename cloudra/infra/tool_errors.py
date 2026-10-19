"""Public validation feedback, without exception dumps or implementation names."""

import json

from pydantic import BaseModel, TypeAdapter, ValidationError


def _schema_location(document: dict, location: tuple):
    """Remove only schema-proven union labels, retaining actual input keys."""
    def resolve(node):
        while "$ref" in node:
            node = document.get("$defs", {}).get(node["$ref"].rsplit("/", 1)[-1], {})
        return node

    def variant(node):
        node = resolve(node)
        fields = node.get("properties", {})
        tags = [f"{name}={field['const']!r}" for name, field in fields.items() if "const" in field]
        return "variant " + (", ".join(tags) if tags else "with fields " + ", ".join(fields))

    def walk(node, remaining, path, parent, parent_path, variants):
        node = resolve(node)
        if not remaining:
            return path, parent, parent_path, variants, node
        part, *rest = remaining
        branches = node.get("anyOf", node.get("oneOf", []))
        if branches:
            mapping = node.get("discriminator", {}).get("mapping", {})
            for branch in branches:
                resolved = resolve(branch)
                labels = {resolved.get("title"), branch.get("$ref", "").rsplit("/", 1)[-1]}
                labels.update(tag for tag, ref in mapping.items() if ref == branch.get("$ref"))
                if part in labels:
                    return walk(branch, rest, path, parent, parent_path, [*variants, variant(branch)])
            # Nullable wrappers have no branch label in Pydantic's loc.
            branch = next((item for item in branches if resolve(item).get("type") != "null"), {})
            return walk(branch, remaining, path, parent, parent_path, variants)
        if isinstance(part, int):
            child = node.get("items", {})
        else:
            child = node.get("properties", {}).get(part)
            if child is None:
                extra = node.get("additionalProperties")
                child = extra if isinstance(extra, dict) else {}
        return walk(child, rest, [*path, part], node, path, variants)

    return walk(document, location, [], {}, [], [])


def validation_feedback(
    exc: ValidationError, *, schema: type[BaseModel] | TypeAdapter, prefix: str = "arguments",
) -> str:
    document = schema.model_json_schema() if isinstance(schema, type) else schema.json_schema()
    issues = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False)[:8]:
        parts, parent, parent_parts, variants, current = _schema_location(document, error["loc"])
        path = ".".join([prefix, *map(str, parts)])
        kind = error["type"]
        if kind == "missing":
            hint = "required field is missing"
        elif kind == "extra_forbidden":
            hint = "field is not accepted here"
        elif kind in {"literal_error", "enum"}:
            hint = error["msg"]
        elif kind in {"union_tag_invalid", "union_tag_not_found"}:
            discriminator = current.get("discriminator", {})
            tag = discriminator.get("propertyName")
            hint = f"missing or invalid operation/type tag {tag!r}" if tag else "missing or invalid operation/type tag"
            if choices := discriminator.get("mapping"):
                hint += "; accepted variants: " + ", ".join(choices)
        else:
            hint = "invalid value; check the field type and constraints in the tool schema"
        if variants:
            hint += " (" + "; ".join(variants) + ")"
        if fields := parent.get("properties"):
            parent_path = ".".join([prefix, *map(str, parent_parts)])
            hint += f"; accepted fields at {parent_path}: " + ", ".join(fields)
            if required := parent.get("required"):
                hint += "; required fields: " + ", ".join(required)
        issues.append(f"{path}: {hint}")
    feedback = "Invalid tool arguments: " + "; ".join(dict.fromkeys(issues))
    properties = document.get("properties", {})
    if set(properties) == {"path", "edits"}:
        feedback += ". Example: " + json.dumps({
            "path": "relative/path.txt", "edits": [{"old_string": "old text", "new_string": "new text"}],
        })
    return feedback
