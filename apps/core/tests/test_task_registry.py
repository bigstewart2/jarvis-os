import pytest

from core.tasks.registry import get_task_manager, set_task_manager


def test_raises_before_a_manager_is_set():
    import core.tasks.registry as registry_module
    registry_module._task_manager = None

    with pytest.raises(RuntimeError):
        get_task_manager()


def test_returns_the_manager_after_set():
    sentinel = object()
    set_task_manager(sentinel)

    assert get_task_manager() is sentinel
