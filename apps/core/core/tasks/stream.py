import json
from dataclasses import dataclass


@dataclass
class TaskEvent:
    stage: str
    detail: dict


def _tool_use_summary(block: dict) -> str:
    tool_input = block.get("input", {})
    if "file_path" in tool_input:
        return str(tool_input["file_path"])
    if "command" in tool_input:
        return str(tool_input["command"])
    if tool_input:
        return str(next(iter(tool_input.values())))
    return ""


def parse_stream_line(line: str) -> TaskEvent | None:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None

    event_type = parsed.get("type")

    if event_type == "assistant":
        content = parsed.get("message", {}).get("content", [])
        for block in content:
            if block.get("type") == "tool_use":
                return TaskEvent(
                    stage="tool_use",
                    detail={"tool": block.get("name", "unknown"), "summary": _tool_use_summary(block)},
                )
        for block in content:
            if block.get("type") == "text":
                text = block.get("text", "")
                return TaskEvent(stage="assistant_text", detail={"text": text[:500]})
        return None

    if event_type == "result":
        return TaskEvent(
            stage="result",
            detail={
                "subtype": parsed.get("subtype"),
                "result": parsed.get("result"),
                "num_turns": parsed.get("num_turns"),
                "duration_ms": parsed.get("duration_ms"),
                "cost_usd": parsed.get("total_cost_usd"),
            },
        )

    return None
