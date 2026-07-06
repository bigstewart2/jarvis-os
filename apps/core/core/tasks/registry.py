_task_manager = None


def set_task_manager(manager) -> None:
    global _task_manager
    _task_manager = manager


def get_task_manager():
    if _task_manager is None:
        raise RuntimeError("TaskManager has not been initialized")
    return _task_manager
