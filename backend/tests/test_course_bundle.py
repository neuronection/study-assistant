import json
import zipfile
from io import BytesIO
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.domain.models import (
    Activity,
    Concept,
    ConceptLink,
    Course,
    Exercise,
    ExerciseStep,
    Extraction,
    Material,
    MaterialIndexCard,
    MaterialLink,
    NodeConcept,
    Note,
    NoteDrawing,
    Question,
    TreeNode,
)
from app.main import create_app


class Scripted(LLMGateway):
    def __init__(self) -> None:
        super().__init__(session_factory=None)

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="m",
            label="m",
            caps=["text", "vision"],
            api_key=None,
        )

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        return "ok"


class NoAI:
    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return None

    def describe(
        self,
        title: str,
        markdown: str,
        course_id: int | None = None,
    ) -> dict[str, Any] | None:
        return None


def make_client(tmp: Any) -> TestClient:
    from pathlib import Path

    app = create_app(
        Settings(data_dir=Path(tmp), log_level="WARNING"),
        gateway=Scripted(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def seed_course(client: TestClient) -> int:
    created = client.post(
        "/api/v1/courses",
        json={"title": "Calculus I", "description": "Single-variable calculus"},
    )
    assert created.status_code == 201, created.text
    course_id = created.json()["id"]
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    root_id = tree[0]["id"]
    child = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root_id, "title": "Derivatives"},
    )
    assert child.status_code == 201, child.text
    node_id = child.json()["id"]

    note = client.post(
        "/api/v1/notes",
        json={
            "title": "Whiteboard",
            "body_md": "see",
            "course_id": course_id,
            "node_id": node_id,
            "tags": ["calc"],
        },
    )
    assert note.status_code == 201, note.text
    note_id = note.json()["id"]

    app_pre = client.app
    assert isinstance(app_pre, FastAPI)
    with app_pre.state.session_factory() as db:
        from app.domain.models import Activity

        activity = Activity(
            profile_id=1,
            course_id=course_id,
            node_id=node_id,
            type="quiz",
            title="Derivatives quiz",
        )
        db.add(activity)
        db.flush()
        db.add(
            Question(
                activity_id=activity.id,
                type="choice",
                stem=[{"type": "text", "md": "d/dx x^2?"}],
                options=[{"type": "text", "md": "2x"}],
                answer={"index": 0},
                explanation=[{"type": "text", "md": "power rule"}],
            )
        )
        db.commit()

    exercise = client.post(
        "/api/v1/exercises",
        json={
            "title": "Differentiate",
            "course_id": course_id,
            "node_id": node_id,
            "steps": [{"prompt_md": "Differentiate $x^3$"}],
        },
    )
    assert exercise.status_code == 201, exercise.text

    app = client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as db:
        from app.pipelines.chunking import chunk_markdown
        from app.storage.fts import sync_material_fts

        stored = app.state.blobs.put(
            b"chain rule original bytes", mime="text/markdown", session=db
        )
        material = Material(
            profile_id=1,
            course_id=course_id,
            kind="md",
            title="Chain rule notes",
            blob_sha=stored.sha256,
            filename="chain-rule.md",
            mime="text/markdown",
            status="ready",
        )
        db.add(material)
        db.flush()
        markdown = "# Chain rule\n\n$(fg)' = f'g + fg'$"
        extraction = Extraction(
            material_id=material.id,
            version=1,
            extractor="manual",
            blocks=[{"type": "text", "md": markdown}],
            markdown=markdown,
        )
        db.add(extraction)
        db.flush()
        for ordinal, text in enumerate(chunk_markdown(markdown)):
            from app.domain.models import Chunk

            db.add(Chunk(extraction_id=extraction.id, ordinal=ordinal, text=text))
        sync_material_fts(db, material, markdown)
        db.add(
            MaterialIndexCard(
                material_id=material.id,
                summary="Chain rule intro",
                topics=["derivatives"],
            )
        )
        db.add(
            MaterialLink(
                course_id=course_id,
                node_id=node_id,
                material_id=material.id,
                rationale="core reading",
            )
        )

        concept = Concept(course_id=course_id, name="chain rule", aliases=["compose"])
        db.add(concept)
        db.flush()
        db.add(NodeConcept(node_id=node_id, concept_id=concept.id, weight=1.0))
        other = Concept(course_id=course_id, name="power rule")
        db.add(other)
        db.flush()
        db.add(
            ConceptLink(
                course_id=course_id,
                from_concept_id=other.id,
                to_concept_id=concept.id,
                relation="related-to",
            )
        )
        png = app.state.blobs.put(b"\x89PNG fake render", mime="image/png", session=db)
        drawing = NoteDrawing(
            note_id=note_id,
            strokes=[{"points": [[0, 0], [5, 5]], "width": 2}],
            png_sha=png.sha256,
        )
        db.add(drawing)
        db.flush()
        note_row = db.get(Note, note_id)
        assert note_row is not None
        note_row.body = [
            {"type": "text", "md": "see"},
            {"type": "drawing", "drawing_id": drawing.id},
        ]
        db.commit()
    return int(course_id)


def test_material_drawings_bundle_round_trip(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        course_id = int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])
        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from app.domain.models import MaterialDrawing

            png = app.state.blobs.put(b"\x89PNG draw", mime="image/png", session=db)
            material = Material(
                profile_id=1,
                course_id=course_id,
                kind="md",
                title="With drawing",
                filename="w.md",
                mime="text/markdown",
                status="ready",
            )
            db.add(material)
            db.flush()
            drawing = MaterialDrawing(
                material_id=material.id,
                strokes=[{"points": [[0, 0]], "width": 2}],
                png_sha=png.sha256,
                view={"x": 10.0, "y": 20.0, "width": 400.0, "height": 200.0},
                ocr_markdown="handwritten limits",
                ocr_version=1,
            )
            db.add(drawing)
            db.flush()
            markdown = f"before\n\n![drawing](ca-drawing://{drawing.id})\n\nafter"
            extraction = Extraction(
                material_id=material.id,
                version=1,
                extractor="manual",
                blocks=[{"type": "text", "md": markdown}],
                markdown=markdown,
            )
            db.add(extraction)
            db.flush()
            db.commit()

        exported = client.get(f"/api/v1/courses/{course_id}/export")
        assert exported.status_code == 200, exported.text
        archive = zipfile.ZipFile(BytesIO(exported.content))
        materials_json = json.loads(archive.read("materials.json"))
        assert len(materials_json[0]["drawings"]) == 1
        assert materials_json[0]["drawings"][0]["ocr_markdown"] == "handwritten limits"
        assert materials_json[0]["drawings"][0]["view"] == {
            "x": 10.0,
            "y": 20.0,
            "width": 400.0,
            "height": 200.0,
        }
        assert f"blobs/{png.sha256}" in archive.namelist()

        imported = client.post(
            "/api/v1/courses/import?dry_run=false", content=exported.content
        )
        assert imported.status_code == 200, imported.text
        new_course_id = imported.json()["imported"]["course_id"]

        materials = client.get(
            "/api/v1/materials", params={"course_id": new_course_id}
        ).json()
        new_material_id = next(
            entry["id"] for entry in materials if entry["title"] == "With drawing"
        )
        detail = client.get(f"/api/v1/materials/{new_material_id}").json()
        assert len(detail["drawings"]) == 1
        imported_drawing_id = detail["drawings"][0]["id"]
        assert detail["drawings"][0]["view"] == {
            "x": 10.0,
            "y": 20.0,
            "width": 400.0,
            "height": 200.0,
        }
        assert imported_drawing_id != materials_json[0]["drawings"][0]["id"]
        assert (
            f"![drawing](ca-drawing://{imported_drawing_id})"
            in detail["extraction"]["markdown"]
        )
        assert (
            f"![drawing](ca-drawing://{materials_json[0]['drawings'][0]['id']})"
            not in detail["extraction"]["markdown"]
        )
        search = client.get("/api/v1/search", params={"q": "handwritten limits"})
        assert search.status_code == 200
        assert any(
            hit["material_id"] == new_material_id for hit in search.json()["hits"]
        )


def test_material_drawings_remap_helpers() -> None:
    from app.services.content.drawings import (
        drawing_ref_ids,
        md_to_blocks,
        remap_drawing_refs,
        strip_drawing_refs,
    )

    md = "a\n\n![drawing](ca-drawing://3)\n\n![sketch](ca-drawing://7) b"
    assert drawing_ref_ids(md) == {3, 7}
    blocks = md_to_blocks(md)
    assert [b["type"] for b in blocks] == ["text", "drawing", "text", "drawing", "text"]
    assert strip_drawing_refs(md, 3) == "a\n\n\n\n![sketch](ca-drawing://7) b"
    assert (
        remap_drawing_refs(md, {3: 9})
        == "a\n\n![drawing](ca-drawing://9)\n\n![sketch](ca-drawing://7) b"
    )


def test_course_bundle_export_import_round_trip(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        course_id = seed_course(client)

        exported = client.get(f"/api/v1/courses/{course_id}/export")
        assert exported.status_code == 200, exported.text
        archive = zipfile.ZipFile(BytesIO(exported.content))
        names = archive.namelist()
        assert "manifest.json" in names
        assert "course.json" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == "ca-course/v2"
        assert manifest["course_title"] == "Calculus I"
        assert manifest["counts"]["quizzes"] == 1
        assert manifest["counts"]["exercises"] == 1
        assert manifest["counts"]["notes"] == 1
        assert manifest["counts"]["card_schedules"] == 0
        assert manifest["counts"]["attempts"] == 0
        assert manifest["warnings"] == []
        blob_names = [name for name in names if name.startswith("blobs/")]
        assert len(blob_names) == 2
        material_sha = json.loads(archive.read("materials.json"))[0]["blob_sha"]
        assert f"blobs/{material_sha}" in blob_names

        preview = client.post(
            "/api/v1/courses/import?dry_run=true", content=exported.content
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["dry_run"] is True
        assert preview.json()["preview"]["title"] == "Calculus I"
        assert preview.json()["preview"]["counts"]["materials"] == 1

        imported = client.post(
            "/api/v1/courses/import?dry_run=false", content=exported.content
        )
        assert imported.status_code == 200, imported.text
        new_course_id = imported.json()["imported"]["course_id"]
        assert new_course_id != course_id
        assert imported.json()["imported"]["title"] == "Calculus I (imported)"

        tree = client.get(f"/api/v1/courses/{new_course_id}/tree").json()
        assert tree[0]["title"] == "Calculus I (imported)"
        assert tree[0]["children"][0]["title"] == "Derivatives"
        new_node_id = tree[0]["children"][0]["id"]

        materials = client.get(
            "/api/v1/materials", params={"course_id": new_course_id}
        ).json()
        titles = [entry["title"] for entry in materials]
        assert "Chain rule notes" in titles
        new_material_id = next(
            entry["id"] for entry in materials if entry["title"] == "Chain rule notes"
        )

        course_materials = client.get(
            f"/api/v1/courses/{new_course_id}/materials"
        ).json()
        assert [
            (entry["material_id"], entry["node_id"], entry["rationale"])
            for entry in course_materials
        ] == [(new_material_id, new_node_id, "core reading")]

        search = client.get("/api/v1/search", params={"q": "chain rule"})
        assert search.status_code == 200
        hits = search.json()["hits"]
        assert any(hit["title"] == "Chain rule notes" for hit in hits)

        notes = client.get(
            "/api/v1/notes", params={"course_id": new_course_id}
        ).json()
        assert [entry["title"] for entry in notes["items"]] == ["Whiteboard"]
        new_note = client.get(f"/api/v1/notes/{notes['items'][0]['id']}").json()
        assert new_note["body"][0]["md"] == "see"
        assert new_note["body"][1]["type"] == "drawing"
        assert len(new_note["drawings"]) == 1

        quizzes = client.get(
            "/api/v1/quiz/activities", params={"course_id": new_course_id}
        ).json()
        assert [entry["title"] for entry in quizzes] == ["Derivatives quiz"]

        exercises = client.get(
            "/api/v1/exercises", params={"course_id": new_course_id}
        ).json()
        assert [entry["title"] for entry in exercises] == ["Differentiate"]

        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from sqlalchemy import select

            from app.domain.models import Activity

            concepts = list(
                db.scalars(select(Concept).where(Concept.course_id == new_course_id))
            )
            assert {concept.name for concept in concepts} == {"chain rule", "power rule"}
            links = list(
                db.scalars(
                    select(ConceptLink).where(ConceptLink.course_id == new_course_id)
                )
            )
            assert len(links) == 1
            coverage = list(
                db.query(NodeConcept).filter(NodeConcept.node_id == new_node_id)
            )
            assert len(coverage) == 1

            activity_ids = list(
                db.scalars(
                    select(Activity.id).where(Activity.course_id == new_course_id)
                )
            )
            questions = list(
                db.query(Question).filter(Question.activity_id.in_(activity_ids))
            )
            assert len(questions) == 1
            assert questions[0].stem[0]["md"] == "d/dx x^2?"

            exercise_ids = list(
                db.scalars(
                    select(Exercise.id).where(Exercise.course_id == new_course_id)
                )
            )
            steps = list(
                db.query(ExerciseStep).filter(
                    ExerciseStep.exercise_id.in_(exercise_ids)
                )
            )
            assert len(steps) == 1

            original_notes = list(
                db.scalars(select(Note.id).where(Note.course_id == course_id))
            )
            original_drawings = list(
                db.query(NoteDrawing).filter(NoteDrawing.note_id.in_(original_notes))
            )
            assert len(original_drawings) == 1
            new_material_rows = list(
                db.scalars(
                    select(Material).where(Material.course_id == new_course_id)
                )
            )
            assert all(row.status == "ready" for row in new_material_rows)
            assert all(row.blob_sha == material_sha for row in new_material_rows)
            assert app.state.blobs.has(material_sha)
            extractions = list(
                db.scalars(
                    select(Extraction).where(
                        Extraction.material_id.in_(
                            [row.id for row in new_material_rows]
                        )
                    )
                )
            )
            assert len(extractions) == 1
            original_links = list(
                db.scalars(
                    select(MaterialLink).where(MaterialLink.course_id == course_id)
                )
            )
            assert len(original_links) == 1
            imported_tree_count = len(
                list(
                    db.scalars(
                        select(TreeNode).where(TreeNode.course_id == new_course_id)
                    )
                )
            )
            assert imported_tree_count == 2


def test_export_handles_non_ascii_course_title(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        created = client.post(
            "/api/v1/courses", json={"title": "Άπειρος Λογισμός"}
        )
        assert created.status_code == 201, created.text
        course_id = created.json()["id"]

        exported = client.get(f"/api/v1/courses/{course_id}/export")
        assert exported.status_code == 200, exported.text
        disposition = exported.headers["content-disposition"]
        assert disposition.startswith("attachment")
        assert "filename*=UTF-8''" in disposition
        assert "%" in disposition
        assert "Ά" not in disposition
        archive = zipfile.ZipFile(BytesIO(exported.content))
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["course_title"] == "Άπειρος Λογισμός"

        preview = client.post(
            "/api/v1/courses/import?dry_run=true", content=exported.content
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["preview"]["title"] == "Άπειρος Λογισμός"


def test_export_degrades_when_blob_files_missing(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        course_id = seed_course(client)
        app = client.app
        assert isinstance(app, FastAPI)
        for path in sorted(app.state.settings.blobs_dir.rglob("*")):
            if path.is_file():
                path.unlink()

        exported = client.get(f"/api/v1/courses/{course_id}/export")
        assert exported.status_code == 200, exported.text
        archive = zipfile.ZipFile(BytesIO(exported.content))
        manifest = json.loads(archive.read("manifest.json"))
        assert any("Chain rule notes" in entry for entry in manifest["warnings"])
        assert any("Whiteboard" in entry for entry in manifest["warnings"])
        assert not [n for n in archive.namelist() if n.startswith("blobs/")]
        materials = json.loads(archive.read("materials.json"))
        assert materials[0]["blob_sha"] is None
        notes = json.loads(archive.read("notes.json"))
        assert notes[0]["drawings"][0]["png_sha"] is None

        preview = client.post(
            "/api/v1/courses/import?dry_run=true", content=exported.content
        )
        assert preview.status_code == 200, preview.text
        assert any(
            "Chain rule notes" in entry
            for entry in preview.json()["preview"]["warnings"]
        )

        imported = client.post(
            "/api/v1/courses/import?dry_run=false", content=exported.content
        )
        assert imported.status_code == 200, imported.text
        new_course_id = imported.json()["imported"]["course_id"]
        materials = client.get(
            "/api/v1/materials", params={"course_id": new_course_id}
        ).json()
        assert [entry["title"] for entry in materials] == ["Chain rule notes"]
        detail = client.get(f"/api/v1/materials/{materials[0]['id']}").json()
        assert detail["material"]["status"] == "ready"
        search = client.get("/api/v1/search", params={"q": "chain rule"})
        assert any(hit["title"] == "Chain rule notes" for hit in search.json()["hits"])


def test_bundle_rejects_bad_archives(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        not_zip = client.post("/api/v1/courses/import", content=b"junk")
        assert not_zip.status_code == 422

        empty_zip = BytesIO()
        with zipfile.ZipFile(empty_zip, "w") as archive:
            archive.writestr("manifest.json", json.dumps({"format": "ca-course/v1"}))
        missing = client.post("/api/v1/courses/import", content=empty_zip.getvalue())
        assert missing.status_code == 422
        assert "missing" in missing.json()["detail"]

        wrong_format = BytesIO()
        with zipfile.ZipFile(wrong_format, "w") as archive:
            archive.writestr("manifest.json", json.dumps({"format": "other/v9"}))
        wrong = client.post("/api/v1/courses/import", content=wrong_format.getvalue())
        assert wrong.status_code == 422
        assert "unsupported" in wrong.json()["detail"]


def test_v2_full_fidelity_round_trip(tmp_path: Any) -> None:
    from datetime import date, timedelta

    from app.domain.models import (
        Answer,
        Attempt,
        ErrorPattern,
        FsrsState,
        NoteVersion,
        ReviewLog,
    )

    client = make_client(tmp_path)
    with client:
        course_id = seed_course(client)
        patched = client.patch(
            f"/api/v1/courses/{course_id}",
            json={"exam_date": str(date.today() + timedelta(days=14))},
        )
        assert patched.status_code == 200, patched.text

        card = client.post(
            "/api/v1/flashcards",
            json={
                "course_id": course_id,
                "kind": "basic",
                "front_md": "d/dx of e^x?",
                "back_md": "e^x",
            },
        )
        assert card.status_code == 201, card.text
        card_id = card.json()["id"]
        reviewed = client.post(f"/api/v1/flashcards/{card_id}/review", json={"rating": 3})
        assert reviewed.status_code == 200, reviewed.text

        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            quiz_activity = (
                db.query(Activity).filter(Activity.course_id == course_id).first()
            )
            assert quiz_activity is not None
            question = (
                db.query(Question).filter(Question.activity_id == quiz_activity.id).first()
            )
            assert question is not None
            attempt = Attempt(activity_id=quiz_activity.id, mode="practice", score=1.0)
            db.add(attempt)
            db.flush()
            db.add(
                Answer(
                    attempt_id=attempt.id,
                    question_id=question.id,
                    correct=True,
                    time_ms=4200,
                )
            )
            db.add(
                ErrorPattern(
                    key="dropped_minus_import",
                    course_type_id=None,
                    name="Dropped minus",
                    description="A minus sign vanished.",
                    is_system=False,
                )
            )
            note_row = db.query(Note).filter(Note.course_id == course_id).first()
            assert note_row is not None
            db.add(
                NoteVersion(
                    note_id=note_row.id,
                    profile_id=1,
                    title="Whiteboard (old)",
                    tags=["calc"],
                    body=[{"type": "text", "md": "older body"}],
                    cause="edit",
                )
            )
            db.commit()

        exported = client.get(
            f"/api/v1/courses/{course_id}/export",
            params={"include_history": "true", "include_note_versions": "true"},
        )
        assert exported.status_code == 200, exported.text
        archive = zipfile.ZipFile(BytesIO(exported.content))
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == "ca-course/v2"
        assert manifest["options"] == {
            "include_history": True,
            "include_note_versions": True,
        }
        assert manifest["counts"]["card_schedules"] == 1
        assert manifest["counts"]["error_patterns"] == 1
        assert manifest["counts"]["attempts"] == 1
        cards_json = json.loads(archive.read("cards.json"))
        assert cards_json[0]["exercise_id"] == card_id
        assert cards_json[0]["state"] != "new"
        assert len(cards_json[0]["reviews"]) == 1
        assert json.loads(archive.read("course.json"))["exam_date"] is not None
        assert len(json.loads(archive.read("note-versions.json"))) == 1

        imported = client.post(
            "/api/v1/courses/import?dry_run=false", content=exported.content
        )
        assert imported.status_code == 200, imported.text
        job_ids = imported.json()["imported"]["postprocess_job_ids"]
        assert len(job_ids) == 1
        new_course_id = imported.json()["imported"]["course_id"]

        with app.state.session_factory() as db:
            from sqlalchemy import select

            new_cards = list(
                db.scalars(select(Exercise).where(Exercise.course_id == new_course_id))
            )
            new_card = next(row for row in new_cards if row.kind.startswith("card_"))
            state = db.scalars(
                select(FsrsState).where(FsrsState.card_id == new_card.id)
            ).one()
            assert state.state == cards_json[0]["state"]
            assert state.reps == 1
            assert (
                len(list(db.scalars(select(ReviewLog).where(ReviewLog.card_id == new_card.id))))
                == 1
            )

            new_course = db.get(Course, new_course_id)
            assert new_course is not None
            assert new_course.exam_date is not None

            patterns = list(
                db.scalars(select(ErrorPattern).where(ErrorPattern.key == "dropped_minus_import"))
            )
            assert len(patterns) == 1
            assert patterns[0].is_system is False

            new_notes = list(db.scalars(select(Note).where(Note.course_id == new_course_id)))
            versions = (
                db.query(NoteVersion).filter(NoteVersion.note_id == new_notes[0].id).all()
            )
            assert len(versions) == 1
            assert versions[0].title == "Whiteboard (old)"

            new_activities = list(
                db.scalars(select(Activity).where(Activity.course_id == new_course_id))
            )
            new_attempts = (
                db.query(Attempt).filter(Attempt.activity_id == new_activities[0].id).all()
            )
            assert len(new_attempts) == 1
            assert new_attempts[0].score == 1.0
            answers = (
                db.query(Answer).filter(Answer.attempt_id == new_attempts[0].id).all()
            )
            assert len(answers) == 1
            assert answers[0].correct is True
            assert answers[0].time_ms == 4200


def test_v2_default_export_omits_history_and_versions(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        course_id = seed_course(client)
        exported = client.get(f"/api/v1/courses/{course_id}/export")
        archive = zipfile.ZipFile(BytesIO(exported.content))
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["options"] == {
            "include_history": False,
            "include_note_versions": False,
        }
        assert json.loads(archive.read("history.json")) == {}
        assert json.loads(archive.read("note-versions.json")) == []


def test_v1_bundle_still_imports(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        course_id = seed_course(client)
        exported = client.get(f"/api/v1/courses/{course_id}/export")
        source = zipfile.ZipFile(BytesIO(exported.content))

        downgraded = BytesIO()
        with zipfile.ZipFile(downgraded, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in source.namelist():
                if name in ("cards.json", "patterns.json", "history.json", "note-versions.json"):
                    continue
                data = source.read(name)
                if name == "manifest.json":
                    manifest = json.loads(data)
                    manifest["format"] = "ca-course/v1"
                    data = json.dumps(manifest).encode()
                archive.writestr(name, data)

        imported = client.post(
            "/api/v1/courses/import?dry_run=false", content=downgraded.getvalue()
        )
        assert imported.status_code == 200, imported.text
        new_course_id = imported.json()["imported"]["course_id"]
        exercises = client.get(
            "/api/v1/exercises", params={"course_id": new_course_id}
        ).json()
        assert [entry["title"] for entry in exercises] == ["Differentiate"]


def test_v2_reexport_is_deterministic(tmp_path: Any) -> None:
    client_a = make_client(tmp_path / "a")
    with client_a:
        course_id = seed_course(client_a)
        first = client_a.get(f"/api/v1/courses/{course_id}/export").content

    client_b = make_client(tmp_path / "b")
    with client_b:
        imported = client_b.post("/api/v1/courses/import?dry_run=false", content=first)
        second_course = imported.json()["imported"]["course_id"]
        assert imported.json()["imported"]["title"] == "Calculus I"
        second = client_b.get(f"/api/v1/courses/{second_course}/export").content

    client_c = make_client(tmp_path / "c")
    with client_c:
        reimported = client_c.post("/api/v1/courses/import?dry_run=false", content=second)
        third_course = reimported.json()["imported"]["course_id"]
        third = client_c.get(f"/api/v1/courses/{third_course}/export").content

    def members(payload: bytes) -> dict[str, Any]:
        archive = zipfile.ZipFile(BytesIO(payload))
        out: dict[str, Any] = {}
        for name in archive.namelist():
            if name.startswith("blobs/"):
                out[name] = archive.read(name)
            elif name == "manifest.json":
                manifest = json.loads(archive.read(name))
                manifest.pop("created_at", None)
                out[name] = manifest
            else:
                out[name] = json.loads(archive.read(name))
        return out

    assert members(second) == members(third)
