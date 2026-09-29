#!/usr/bin/env python
"""Provision the demo scripted tutor for UI capture (family demo-tour
standard — same idea as Health Assistant seeding its mock provider for
demos).

Registers the local scripted mock provider (frontend/e2e/mock_provider.py)
as the instance's text/embeddings model, so tutor chat produces
deterministic, rich demo answers (math, charts, tool cards, proposal
cards) with no API key. Idempotent.

Guarded like the content seeder: the target must be a demo database
(instance_settings.demo_mode = true) — anything else is refused.

Usage (with the app's dependencies, e.g. via uv from the repo root):

    python scripts/ui-capture/seed-demo-ai.py --demo-dir dev/demo-data \
        --base-url http://127.0.0.1:8321/v1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from sqlalchemy import select  # noqa: E402

from app.domain.models.ops import (  # noqa: E402
    AiModel,
    DefaultTaskAssignment,
    Provider,
)
from app.storage.db import make_engine, make_session_factory  # noqa: E402

PROVIDER_NAME = "Demo scripted tutor (local mock)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", default=str(ROOT / "dev" / "demo-data"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8321/v1")
    args = parser.parse_args()

    demo_dir = Path(args.demo_dir).resolve()
    db_path = demo_dir / "study.sqlite3"
    if not db_path.is_file():
        print(f"refusing: {db_path} does not exist — run scripts/ui-capture/seed-demo.sh first")
        return 2

    engine = make_engine(f"sqlite:///{db_path}")
    session = make_session_factory(engine)()
    try:
        # Instance guard (identity-auth §13): demo AI config is provisioned
        # only on demo instances.
        from sqlalchemy import text

        demo_mode = session.execute(
            text("SELECT value FROM instance_settings WHERE key = 'demo_mode'")
        ).scalar()
        if demo_mode != "true":
            print("refusing: instance_settings.demo_mode is not 'true' — not a demo instance")
            return 2

        provider = session.execute(
            select(Provider).where(Provider.name == PROVIDER_NAME)
        ).scalar_one_or_none()
        if provider is None:
            provider = Provider(
                name=PROVIDER_NAME,
                type="openai_compatible",
                base_url=args.base_url,
                keyring_ref="",
                enabled=True,
                is_local=True,
            )
            session.add(provider)
            session.flush()
            print(f"provider created: {PROVIDER_NAME} → {args.base_url}")
        else:
            provider.base_url = args.base_url
            print(f"provider present: {PROVIDER_NAME}")

        models = {}
        for external_id, label, caps in (
            ("mock-text", "Demo scripted tutor", ["text"]),
            ("mock-embed", "Demo scripted embeddings", ["embeddings"]),
        ):
            model = session.execute(
                select(AiModel).where(
                    AiModel.provider_id == provider.id, AiModel.external_id == external_id
                )
            ).scalar_one_or_none()
            if model is None:
                model = AiModel(
                    provider_id=provider.id,
                    external_id=external_id,
                    label=label,
                    caps=caps,
                    enabled=True,
                )
                session.add(model)
                session.flush()
                print(f"model created: {external_id} ({caps[0]})")
            elif not model.enabled:
                model.enabled = True
            models[external_id] = model

        for requires, external_id in (("text", "mock-text"), ("embeddings", "mock-embed")):
            assignment = session.get(DefaultTaskAssignment, requires)
            if assignment is None:
                session.add(
                    DefaultTaskAssignment(requires=requires, model_id=models[external_id].id)
                )
                print(f"task default set: {requires} → {external_id}")
            elif assignment.model_id != models[external_id].id:
                assignment.model_id = models[external_id].id
                print(f"task default updated: {requires} → {external_id}")

        session.commit()
        print("demo AI provisioning: OK")
        return 0
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
