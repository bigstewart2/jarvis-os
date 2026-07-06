import re

TOKEN_PATTERN = re.compile(r"\{\{steps\.(\d+)\.([\w.]+)\}\}")
_WHOLE_TOKEN_PATTERN = re.compile(r"^\{\{steps\.(\d+)\.([\w.]+)\}\}$")


class RenderError(Exception):
    pass


def _resolve_path(step_outputs: list[dict], index: int, path: str):
    if index < 0 or index >= len(step_outputs):
        raise RenderError(f"step index {index} out of range (have {len(step_outputs)} prior step outputs)")
    value = step_outputs[index]
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise RenderError(f"path '{path}' not found in step {index}'s outputs")
        value = value[part]
    return value


def _render_string(template: str, step_outputs: list[dict]):
    whole_match = _WHOLE_TOKEN_PATTERN.match(template)
    if whole_match:
        index = int(whole_match.group(1))
        path = whole_match.group(2)
        return _resolve_path(step_outputs, index, path)

    def _replace(match: "re.Match") -> str:
        index = int(match.group(1))
        path = match.group(2)
        return str(_resolve_path(step_outputs, index, path))

    return TOKEN_PATTERN.sub(_replace, template)


def render_inputs(template, step_outputs: list[dict]):
    if isinstance(template, str):
        return _render_string(template, step_outputs)
    if isinstance(template, dict):
        return {key: render_inputs(value, step_outputs) for key, value in template.items()}
    if isinstance(template, list):
        return [render_inputs(item, step_outputs) for item in template]
    return template


def extract_referenced_step_indices(template) -> set:
    indices: set = set()
    if isinstance(template, str):
        for match in TOKEN_PATTERN.finditer(template):
            indices.add(int(match.group(1)))
    elif isinstance(template, dict):
        for value in template.values():
            indices |= extract_referenced_step_indices(value)
    elif isinstance(template, list):
        for item in template:
            indices |= extract_referenced_step_indices(item)
    return indices
