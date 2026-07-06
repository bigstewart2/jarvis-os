import json

from core.tasks.stream import TaskEvent, parse_stream_line


def test_parses_tool_use_event_with_file_path():
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "foo.py"}}]},
    })

    event = parse_stream_line(line)

    assert event == TaskEvent(stage="tool_use", detail={"tool": "Edit", "summary": "foo.py"})


def test_parses_tool_use_event_with_command():
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "git status"}}]},
    })

    event = parse_stream_line(line)

    assert event == TaskEvent(stage="tool_use", detail={"tool": "Bash", "summary": "git status"})


def test_parses_assistant_text_event_and_truncates_to_500_chars():
    long_text = "x" * 600
    line = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": long_text}]}})

    event = parse_stream_line(line)

    assert event.stage == "assistant_text"
    assert event.detail["text"] == "x" * 500


def test_tool_use_takes_priority_over_text_in_the_same_message():
    line = json.dumps({
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "About to edit a file."},
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "bar.py"}},
            ]
        },
    })

    event = parse_stream_line(line)

    assert event == TaskEvent(stage="tool_use", detail={"tool": "Edit", "summary": "bar.py"})


def test_parses_result_event():
    line = json.dumps({
        "type": "result",
        "subtype": "success",
        "result": "Done.",
        "num_turns": 3,
        "duration_ms": 1200,
        "total_cost_usd": 0.05,
    })

    event = parse_stream_line(line)

    assert event == TaskEvent(
        stage="result",
        detail={
            "subtype": "success",
            "result": "Done.",
            "num_turns": 3,
            "duration_ms": 1200,
            "cost_usd": 0.05,
        },
    )


def test_skips_system_event():
    assert parse_stream_line(json.dumps({"type": "system", "subtype": "init"})) is None


def test_skips_user_event():
    assert parse_stream_line(json.dumps({"type": "user", "message": {}})) is None


def test_returns_none_for_malformed_json():
    assert parse_stream_line("not json at all") is None


def test_returns_none_for_blank_line():
    assert parse_stream_line("   \n") is None


def test_returns_none_for_non_dict_json():
    assert parse_stream_line("[1, 2, 3]") is None
