import pytest

from core.automation.template import RenderError, extract_referenced_step_indices, render_inputs


def test_whole_string_token_preserves_type():
    result = render_inputs("{{steps.0.response}}", [{"response": {"nested": "value"}}])
    assert result == {"nested": "value"}


def test_embedded_token_stringifies():
    result = render_inputs("Say: {{steps.0.response}}", [{"response": "hello"}])
    assert result == "Say: hello"


def test_nested_dict_and_list_recursion():
    template = {"a": ["{{steps.0.x}}", {"b": "{{steps.0.y}}"}]}
    result = render_inputs(template, [{"x": "1", "y": "2"}])
    assert result == {"a": ["1", {"b": "2"}]}


def test_dotted_path_traversal():
    result = render_inputs("{{steps.0.a.b}}", [{"a": {"b": "deep"}}])
    assert result == "deep"


def test_missing_key_raises_render_error():
    with pytest.raises(RenderError):
        render_inputs("{{steps.0.missing}}", [{"response": "hi"}])


def test_non_dict_traversal_raises_render_error():
    with pytest.raises(RenderError):
        render_inputs("{{steps.0.a.b}}", [{"a": "not a dict"}])


def test_out_of_range_index_raises_render_error():
    with pytest.raises(RenderError):
        render_inputs("{{steps.5.response}}", [{"response": "hi"}])


def test_multiple_tokens_in_one_string():
    result = render_inputs("{{steps.0.a}} and {{steps.1.b}}", [{"a": "x"}, {"b": "y"}])
    assert result == "x and y"


def test_token_free_template_passes_through():
    result = render_inputs("plain text", [{"a": "x"}])
    assert result == "plain text"


def test_non_string_scalar_passes_through():
    result = render_inputs(42, [{"a": "x"}])
    assert result == 42


def test_extract_referenced_step_indices_finds_all_indices():
    template = {"a": "{{steps.0.x}}", "b": ["{{steps.2.y}}", "no token here"]}
    assert extract_referenced_step_indices(template) == {0, 2}


def test_extract_referenced_step_indices_empty_for_no_tokens():
    assert extract_referenced_step_indices({"a": "plain", "b": 42}) == set()
