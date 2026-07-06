from core.db.database import init_db, make_engine, make_session_factory
from core.db.models import SkillInvocation


def test_create_and_query_invocation():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        row = SkillInvocation(
            skill_id="echo",
            inputs={"text": "hello"},
            outputs={"text": "hello"},
            status="completed",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        assert row.id is not None

    with session_factory() as session:
        fetched = session.query(SkillInvocation).filter_by(skill_id="echo").one()
        assert fetched.inputs == {"text": "hello"}
        assert fetched.outputs == {"text": "hello"}
        assert fetched.status == "completed"


def test_route_decision_can_be_created_and_queried():
    from core.db.models import RouteDecision

    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        session.add(
            RouteDecision(
                transcript="what time is it",
                raw_response='{"skill_id": "ask", "inputs": {}}',
                skill_id="ask",
                fallback_used=True,
                fallback_reason="model_chose_ask",
            )
        )
        session.commit()

    with session_factory() as session:
        row = session.query(RouteDecision).one()
        assert row.transcript == "what time is it"
        assert row.skill_id == "ask"
        assert row.fallback_used is True
        assert row.fallback_reason == "model_chose_ask"
        assert row.created_at is not None
