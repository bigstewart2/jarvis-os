from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from core.db.models import SkillInvocation


class SkillNotFoundError(Exception):
    pass


async def invoke_and_record_skill(app: FastAPI, skill_id: str, inputs: dict) -> tuple[str, dict]:
    loaded = app.state.registry.get(skill_id)
    if loaded is None:
        raise SkillNotFoundError(skill_id)

    status = "completed"
    try:
        outputs = await run_in_threadpool(loaded.run, inputs)
    except Exception as exc:
        status = "failed"
        outputs = {"error": str(exc)}

    with app.state.session_factory() as session:
        session.add(
            SkillInvocation(skill_id=skill_id, inputs=inputs, outputs=outputs, status=status)
        )
        session.commit()

    await app.state.event_bus.publish(
        {"type": "skill_invoked", "skill_id": skill_id, "status": status, "outputs": outputs}
    )
    return status, outputs
