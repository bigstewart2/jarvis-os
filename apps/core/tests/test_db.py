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
