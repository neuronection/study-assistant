from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.models import Artifact, Profile
from app.services.artifacts.daily import run_daily_briefs


def test_daily_brief_runs_once_after_its_time(client: TestClient) -> None:
    with client:
        course = client.post("/api/v1/courses", json={"title": "Daily brief course"})
        assert course.status_code == 201
        settings = client.app.state.settings  # type: ignore[attr-defined]
        engine = create_engine(f"sqlite:///{settings.db_path}")
        with sessionmaker(bind=engine)() as session:
            profile = session.scalars(select(Profile)).first()
            assert profile is not None
            profile.preferences = {
                **(profile.preferences or {}),
                "daily_brief": {"enabled": True, "time": "00:00", "length_minutes": 5},
            }
            session.commit()
        engine.dispose()

        assert run_daily_briefs(client.app.state.session_factory) == 1  # type: ignore[attr-defined]
        assert run_daily_briefs(client.app.state.session_factory) == 0  # type: ignore[attr-defined]

        with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
            artifacts = list(
                session.scalars(
                    select(Artifact).where(Artifact.kind == "audio_brief")
                )
            )
            assert len(artifacts) == 1
            assert artifacts[0].spec["chapters"]
