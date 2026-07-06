import uuid
from pathlib import Path

from fastapi.concurrency import run_in_threadpool

from core.config import Settings, get_settings
from core.db.models import RouteDecision
from core.providers.llm.factory import get_llm_provider
from core.routing.intent_router import route
from core.skills.invocation import SkillNotFoundError, invoke_and_record_skill
from core.voice.files import prune_tts_files, tts_path, upload_path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _log_route_decision(
    app, transcript: str, skill_id: str, raw_response: str, fallback_used: bool, fallback_reason: str | None
) -> None:
    with app.state.session_factory() as session:
        session.add(
            RouteDecision(
                transcript=transcript,
                raw_response=raw_response,
                skill_id=skill_id,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
            )
        )
        session.commit()


def _derive_response_text(outputs: dict, skill_id: str) -> str:
    response = outputs.get("response")
    if isinstance(response, str):
        return response
    for value in outputs.values():
        if isinstance(value, str):
            return value
    return f"Done — {skill_id} completed."


async def _publish(app, invocation_id: str, stage: str, detail: dict) -> None:
    await app.state.event_bus.publish(
        {"type": "voice_status", "invocation_id": invocation_id, "stage": stage, "detail": detail}
    )


async def run_voice_pipeline(app, audio_bytes: bytes, upload_extension: str) -> dict:
    settings: Settings = get_settings()
    invocation_id = str(uuid.uuid4())
    voice_dir = BASE_DIR / settings.voice_dir
    prune_tts_files(voice_dir)

    result = {
        "invocation_id": invocation_id,
        "transcript": "",
        "skill_id": None,
        "fallback_used": False,
        "fallback_reason": None,
        "outputs": None,
        "response_text": "",
        "audio_url": None,
        "error": None,
    }

    async def _speak_and_finish(text: str, error: str | None) -> dict:
        result["response_text"] = text
        result["error"] = error
        try:
            output_path = tts_path(voice_dir)
            await run_in_threadpool(app.state.tts_provider.synthesize, text, output_path)
            result["audio_url"] = f"/voice/audio/{output_path.stem}"
        except Exception as exc:
            tts_error = f"tts_failed: {exc}"
            result["error"] = f"{error}; {tts_error}" if error else tts_error
        stage = "error" if result["error"] else "done"
        await _publish(app, invocation_id, stage, {"message": result["error"]} if result["error"] else {})
        return result

    upload = upload_path(voice_dir, extension=upload_extension)
    upload.write_bytes(audio_bytes)

    await _publish(app, invocation_id, "transcribing", {})
    try:
        transcript = await run_in_threadpool(app.state.stt_provider.transcribe, upload)
    except Exception as exc:
        upload.unlink(missing_ok=True)
        return await _speak_and_finish("I couldn't process that audio.", f"stt_failed: {exc}")
    upload.unlink(missing_ok=True)

    transcript = transcript.strip()
    result["transcript"] = transcript
    if not transcript:
        return await _speak_and_finish("I didn't catch that.", "empty_transcript")

    await _publish(app, invocation_id, "routing", {"transcript": transcript})
    manifests = app.state.registry.list()
    llm = get_llm_provider(settings)
    try:
        route_result = await run_in_threadpool(route, transcript, manifests, llm)
    except Exception as exc:
        return await _speak_and_finish("I couldn't reach the language model.", f"routing_failed: {exc}")

    _log_route_decision(
        app,
        transcript,
        route_result.skill_id,
        route_result.raw_response,
        route_result.fallback_used,
        route_result.fallback_reason,
    )
    result["skill_id"] = route_result.skill_id
    result["fallback_used"] = route_result.fallback_used
    result["fallback_reason"] = route_result.fallback_reason

    await _publish(
        app,
        invocation_id,
        "invoking_skill",
        {"skill_id": route_result.skill_id, "fallback_used": route_result.fallback_used},
    )
    try:
        status, outputs = await invoke_and_record_skill(app, route_result.skill_id, route_result.inputs)
    except SkillNotFoundError:
        # route() already validates skill_id against the registry at routing time;
        # this branch only guards a concurrent-registry-change race that cannot
        # happen in this single-process app, but keeps the pipeline's always-respond
        # guarantee true even in that theoretical case.
        return await _speak_and_finish(
            "Something went wrong routing your request.",
            f"route_skill_missing: {route_result.skill_id}",
        )
    result["outputs"] = outputs

    if status == "failed":
        return await _speak_and_finish(
            f"The {route_result.skill_id} skill failed.", f"skill_failed: {outputs.get('error')}"
        )

    await _publish(app, invocation_id, "synthesizing", {"skill_id": route_result.skill_id})
    response_text = _derive_response_text(outputs, route_result.skill_id)
    return await _speak_and_finish(response_text, None)
