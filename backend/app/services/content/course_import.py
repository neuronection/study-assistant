from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions.errors import ExtensionError

from ...domain.models import (
    Activity,
    Answer,
    Attempt,
    Chunk,
    Concept,
    ConceptLink,
    Course,
    CourseDefaultTaskAssignment,
    CourseTaskAssignment,
    ErrorPattern,
    Exercise,
    ExerciseSession,
    ExerciseStep,
    ExternalSource,
    Extraction,
    FsrsState,
    Material,
    MaterialDrawing,
    MaterialFolder,
    MaterialFolderLink,
    MaterialIndexCard,
    MaterialLink,
    NodeConcept,
    Note,
    NoteDrawing,
    NoteVersion,
    Question,
    QuizHelpEvent,
    ReviewLog,
    Skill,
    SkillVersion,
    StepAttempt,
    TreeNode,
    new_uuid,
    utcnow,
)
from ...services.retrieval.chunk_profile import chunk_texts_for_space
from ...storage.fts import sync_material_fts
from .course_validate import (
    BundleData,
    BundleError,
)
from .drawings import apply_drawing_view, remap_drawing_refs
from .external_sources import validate_source as validate_external_source
from .folders import FoldersService
from .materials import extraction_to_blocks


def _bundle_view(drawing: dict[str, Any]) -> dict[str, float] | None:
    view = drawing.get("view")
    if not isinstance(view, dict):
        return None
    try:
        return {
            "x": float(view["x"]),
            "y": float(view["y"]),
            "width": float(view["width"]),
            "height": float(view["height"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def bundle_preview(bundle: BundleData) -> dict[str, Any]:
    counts = bundle.manifest.get("counts", {})
    warnings = [str(entry) for entry in bundle.manifest.get("warnings", [])]
    for material in bundle.materials:
        if material.get("extraction") is None:
            warnings.append(f"material '{material.get('title')}' has no extraction")
    return {
        "title": bundle.course.get("title"),
        "counts": counts,
        "warnings": warnings,
    }


def _import_id(session: Session, model: Any, incoming: Any, taken: set[str]) -> str:
    candidate = str(incoming) if incoming is not None else ""
    if candidate and candidate not in taken and session.get(model, candidate) is None:
        taken.add(candidate)
        return candidate
    generated = new_uuid()
    taken.add(generated)
    return generated


def import_course_bundle(
    session: Session,
    bundle: BundleData,
    profile_id: str,
    blobs_root: Path,
    blob_store: Any,
    existing_titles: set[str],
) -> dict[str, Any]:
    from ..knowledge.tree import TreeService

    course_data = cast(dict[str, Any], bundle.course)
    tree_data = cast(list[dict[str, Any]], bundle.tree)
    concepts_data = cast(dict[str, Any], bundle.concepts)
    folders_data = cast(dict[str, Any], bundle.folders)
    materials_data = cast(list[dict[str, Any]], bundle.materials)

    title = str(course_data["title"]).strip()[:300]
    imported_title = title
    if imported_title in existing_titles:
        imported_title = f"{title[:280]} (imported)"

    raw_exam_date = course_data.get("exam_date")
    exam_date = None
    if raw_exam_date:
        try:
            exam_date = date.fromisoformat(str(raw_exam_date))
        except ValueError as error:
            raise BundleError(f"invalid exam_date: {raw_exam_date!r}") from error

    taken: set[str] = set()
    course = Course(
        id=_import_id(session, Course, course_data.get("id"), taken),
        profile_id=profile_id,
        title=imported_title,
        description=course_data.get("description"),
        subject=course_data.get("subject"),
        level=course_data.get("level"),
        goals=course_data.get("goals"),
        tags=course_data.get("tags"),
        color=course_data.get("color"),
        exam_date=exam_date,
    )
    session.add(course)
    session.flush()

    for entry in bundle.task_assignments:
        if entry.get("kind") == "default":
            requires = str(entry.get("requires") or "").strip()
            if not requires:
                continue
            session.add(
                CourseDefaultTaskAssignment(
                    course_id=course.id,
                    requires=requires,
                    model_id=entry.get("model_id"),
                )
            )
            continue
        task = str(entry.get("task") or "").strip()
        if not task:
            continue
        session.add(
            CourseTaskAssignment(
                course_id=course.id,
                task=task,
                model_id=entry.get("model_id"),
                fallback_model_id=entry.get("fallback_model_id"),
            )
        )
    session.flush()

    tree = TreeService(session)
    root_entry = next((entry for entry in tree_data if entry.get("is_root")), None)
    root = tree.ensure_root(
        course.id,
        node_id=(_import_id(session, TreeNode, root_entry["id"], taken) if root_entry else None),
    )
    node_map: dict[str, str] = {}
    for entry in tree_data:
        if entry.get("is_root"):
            node_map[str(entry["id"])] = root.id
            if entry.get("ai_hint"):
                root.ai_hint = entry["ai_hint"]
            if entry.get("summary"):
                root.summary = entry["summary"]
            continue
    pending = [entry for entry in tree_data if not entry.get("is_root")]
    pending.sort(key=lambda entry: (entry.get("depth", 1), entry.get("order_idx", 0), entry["id"]))
    for entry in pending:
        created = tree.create_node(
            course.id,
            node_map[str(entry["parent_id"])],
            entry["title"],
            summary=entry.get("summary"),
            objectives=entry.get("objectives"),
            ai_hint=entry.get("ai_hint"),
            node_id=_import_id(session, TreeNode, entry["id"], taken),
        )
        node_map[str(entry["id"])] = created.id
    session.flush()

    concept_map: dict[str, str] = {}
    for entry in concepts_data.get("concepts", []):
        concept = Concept(
            id=_import_id(session, Concept, entry["id"], taken),
            course_id=course.id,
            name=str(entry["name"])[:200],
            description=entry.get("description"),
            aliases=entry.get("aliases"),
        )
        session.add(concept)
        session.flush()
        concept_map[str(entry["id"])] = concept.id
    for link in concepts_data.get("links", []):
        session.add(
            ConceptLink(
                course_id=course.id,
                from_concept_id=concept_map[str(link["from_concept_id"])],
                to_concept_id=concept_map[str(link["to_concept_id"])],
                relation=link["relation"],
            )
        )
    for coverage in concepts_data.get("coverage", []):
        session.add(
            NodeConcept(
                node_id=node_map[str(coverage["node_id"])],
                concept_id=concept_map[str(coverage["concept_id"])],
                weight=coverage.get("weight"),
            )
        )
    session.flush()

    folder_map: dict[str, str] = {}
    folders_service = FoldersService(session)
    for entry in sorted(folders_data.get("folders", []), key=lambda item: str(item.get("path"))):
        path = str(entry.get("path") or "")
        name = str(entry.get("name") or path.rsplit("/", 1)[-1])
        parent_path = path.rsplit("/", 1)[0] if "/" in path else None
        parent_id = folder_map.get(parent_path) if parent_path is not None else None
        folder = folders_service.create(
            profile_id=profile_id,
            name=name,
            course_id=course.id,
            parent_id=parent_id,
            folder_id=_import_id(session, MaterialFolder, entry.get("id"), taken),
        )
        folder_map[path] = folder.id
    for link in folders_data.get("links", []):
        session.add(
            MaterialFolderLink(
                course_id=course.id,
                node_id=node_map[str(link["node_id"])],
                folder_id=folder_map[str(link["folder_path"])],
                rationale=link.get("rationale"),
                auto_assigned=bool(link.get("auto_assigned")),
                confidence=link.get("confidence"),
            )
        )
    session.flush()

    material_map: dict[str, str] = {}
    postprocess_job_ids: list[str] = []
    for entry in materials_data:
        sha = entry.get("blob_sha")
        if sha is not None:
            mime = entry.get("mime") or "application/octet-stream"
            blob_store.put(bundle.blobs[sha], mime=mime, session=session)
        entry_folder_path = entry.get("folder_path")
        material = Material(
            id=_import_id(session, Material, entry["id"], taken),
            profile_id=profile_id,
            course_id=course.id,
            folder_id=(
                folder_map[entry_folder_path]
                if isinstance(entry_folder_path, str) and entry_folder_path in folder_map
                else None
            ),
            kind=str(entry.get("kind") or "document"),
            title=str(entry.get("title") or "Material")[:300],
            blob_sha=sha,
            filename=str(entry.get("filename") or "material.md")[:500],
            mime=entry.get("mime"),
            pages=entry.get("pages"),
            language=entry.get("language"),
            status="ready",
            provenance=entry.get("provenance"),
            source_url=entry.get("source_url"),
            source_url_norm=entry.get("source_url_norm"),
            tags=entry.get("tags"),
            starred=bool(entry.get("starred") or False),
        )
        session.add(material)
        session.flush()
        material_map[str(entry["id"])] = material.id

        drawing_map: dict[str, str] = {}
        for drawing in entry.get("drawings", []):
            drawing_sha = drawing.get("png_sha")
            if drawing_sha is not None:
                blob_store.put(bundle.blobs[drawing_sha], mime="image/png", session=session)
            previous_id = str(drawing.get("id") or "")
            material_drawing_row = MaterialDrawing(
                id=_import_id(session, MaterialDrawing, drawing.get("id"), taken),
                material_id=material.id,
                strokes=drawing.get("strokes") or [],
                png_sha=drawing_sha,
                ocr_version=int(drawing.get("ocr_version") or 0),
                ocr_blocks=drawing.get("ocr_blocks"),
                ocr_markdown=drawing.get("ocr_markdown"),
            )
            apply_drawing_view(material_drawing_row, _bundle_view(drawing))
            session.add(material_drawing_row)
            session.flush()
            if previous_id:
                drawing_map[previous_id] = material_drawing_row.id
        drawing_ocr = "\n".join(
            d["ocr_markdown"] for d in entry.get("drawings", []) if d.get("ocr_markdown")
        )

        extraction = entry.get("extraction")
        if extraction is not None:
            markdown = remap_drawing_refs(str(extraction.get("markdown") or ""), drawing_map)
            row = Extraction(
                material_id=material.id,
                version=int(extraction.get("version") or 1),
                extractor=str(extraction.get("extractor") or "import"),
                model=extraction.get("model"),
                blocks=extraction_to_blocks(markdown),
                markdown=markdown,
                language=extraction.get("language"),
                reviewed=bool(extraction.get("reviewed")),
            )
            session.add(row)
            session.flush()
            chunk_source = f"{markdown}\n\n{drawing_ocr}" if drawing_ocr else markdown
            for ordinal, (chunk_text, chunk_tokens) in enumerate(
                chunk_texts_for_space(session, chunk_source)
            ):
                session.add(
                    Chunk(
                        extraction_id=row.id,
                        ordinal=ordinal,
                        text=chunk_text,
                        token_count=chunk_tokens,
                    )
                )
            sync_material_fts(session, material, markdown, drawing_ocr)
        card = entry.get("index_card")
        if card is not None:
            session.add(
                MaterialIndexCard(
                    material_id=material.id,
                    summary=card.get("summary"),
                    topics=card.get("topics"),
                    key_terms=card.get("key_terms"),
                    reading_minutes=card.get("reading_minutes"),
                    difficulty=card.get("difficulty"),
                )
            )
        for link in entry.get("links", []):
            session.add(
                MaterialLink(
                    course_id=course.id,
                    node_id=node_map[str(link["node_id"])],
                    material_id=material.id,
                    rationale=link.get("rationale"),
                    auto_assigned=bool(link.get("auto_assigned")),
                    confidence=link.get("confidence"),
                )
            )
        session.flush()
        from ...jobs.runner import JobRunner

        postprocess_job_ids.append(
            JobRunner.enqueue(session, "postprocess", {"material_id": material.id}).id
        )

    note_map: dict[str, str] = {}
    for entry in bundle.notes:
        note = Note(
            id=_import_id(session, Note, entry["id"], taken),
            profile_id=profile_id,
            course_id=course.id,
            node_id=(node_map[str(entry["node_id"])] if entry.get("node_id") is not None else None),
            owner_type="standalone",
            owner_id=None,
            title=str(entry.get("title") or "Note")[:300],
            body=entry.get("body") or [],
            tags=entry.get("tags"),
            pinned=bool(entry.get("pinned")),
        )
        note.search_text = str(note.title)
        session.add(note)
        session.flush()
        note_map[str(entry["id"])] = note.id
        for drawing in entry.get("drawings", []):
            sha = drawing.get("png_sha")
            if sha is not None:
                blob_store.put(bundle.blobs[sha], mime="image/png", session=session)
            drawing_row = NoteDrawing(
                id=_import_id(session, NoteDrawing, drawing.get("id"), taken),
                note_id=note.id,
                strokes=drawing.get("strokes") or [],
                png_sha=sha,
                ocr_version=int(drawing.get("ocr_version") or 0),
                ocr_blocks=drawing.get("ocr_blocks"),
                ocr_markdown=drawing.get("ocr_markdown"),
            )
            apply_drawing_view(drawing_row, _bundle_view(drawing))
            session.add(drawing_row)
            if drawing.get("ocr_markdown"):
                note.search_text = f"{note.search_text}\n{drawing['ocr_markdown']}"
        session.flush()

    for version in bundle.note_versions:
        session.add(
            NoteVersion(
                id=_import_id(session, NoteVersion, version.get("id"), taken),
                note_id=note_map[str(version["note_id"])],
                profile_id=profile_id,
                title=str(version.get("title") or "Note")[:300],
                tags=version.get("tags"),
                body=version.get("body") or [],
                cause=str(version.get("cause") or "import"),
                created_at=_parse_datetime(version.get("created_at")) or utcnow(),
            )
        )
    session.flush()

    question_map: dict[str, str] = {}
    attempt_map: dict[str, str] = {}
    session_map: dict[str, str] = {}
    activity_map: dict[str, str] = {}
    for entry in bundle.quizzes:
        activity = Activity(
            id=_import_id(session, Activity, entry["id"], taken),
            profile_id=profile_id,
            course_id=course.id,
            node_id=(node_map[str(entry["node_id"])] if entry.get("node_id") is not None else None),
            type=str(entry.get("type") or "quiz"),
            title=str(entry.get("title") or "Quiz")[:300],
            config=entry.get("config"),
        )
        session.add(activity)
        session.flush()
        activity_map[str(entry["id"])] = activity.id
        for question in entry.get("questions", []):
            concept_ids = question.get("concept_ids") or []
            remapped = [concept_map[str(cid)] for cid in concept_ids if str(cid) in concept_map]
            question_row = Question(
                id=_import_id(session, Question, question.get("id"), taken),
                activity_id=activity.id,
                type=str(question.get("type") or "single"),
                stem=question.get("stem") or [{"type": "text", "md": ""}],
                options=question.get("options"),
                answer=question.get("answer") or {},
                explanation=question.get("explanation"),
                difficulty=question.get("difficulty"),
                bloom=question.get("bloom"),
                skill=question.get("skill"),
                concept_ids=remapped or None,
                expected_time_sec=question.get("expected_time_sec"),
                curriculum_code=question.get("curriculum_code"),
                distractor_misconceptions=question.get("distractor_misconceptions"),
                sympy_check=question.get("sympy_check"),
                input_modes=question.get("input_modes"),
                tags=question.get("tags"),
                flag=str(question.get("flag") or "ok"),
            )
            session.add(question_row)
            session.flush()
            if question.get("id") is not None:
                question_map[str(question["id"])] = question_row.id

    exercise_map: dict[str, str] = {}
    for entry in bundle.exercises:
        exercise = Exercise(
            id=_import_id(session, Exercise, entry["id"], taken),
            profile_id=profile_id,
            course_id=course.id,
            node_id=(node_map[str(entry["node_id"])] if entry.get("node_id") is not None else None),
            title=str(entry.get("title") or "Exercise")[:300],
            kind=str(entry.get("kind") or "multi_step"),
            deck_ref=entry.get("deck_ref"),
            context=entry.get("context"),
            difficulty=entry.get("difficulty"),
            created_from=entry.get("created_from"),
        )
        session.add(exercise)
        session.flush()
        exercise_map[str(entry["id"])] = exercise.id
        for step in entry.get("steps", []):
            session.add(
                ExerciseStep(
                    id=_import_id(session, ExerciseStep, step.get("id"), taken),
                    exercise_id=exercise.id,
                    order_idx=int(step.get("order_idx") or 0),
                    prompt=step.get("prompt") or [{"type": "text", "md": ""}],
                    expected=step.get("expected"),
                    hints_pregenerated=step.get("hints_pregenerated"),
                    rubric=step.get("rubric"),
                )
            )
        session.flush()

    for card in bundle.cards:
        due_at = _parse_datetime(card.get("due_at"))
        session.add(
            FsrsState(
                id=_import_id(session, FsrsState, card.get("id"), taken),
                card_id=exercise_map[str(card["exercise_id"])],
                state=str(card.get("state") or "new"),
                stability=card.get("stability"),
                difficulty=card.get("difficulty"),
                reps=int(card.get("reps") or 0),
                lapses=int(card.get("lapses") or 0),
                due_at=due_at or utcnow(),
                last_review_at=_parse_datetime(card.get("last_review_at")),
            )
        )
        for review in card.get("reviews", []):
            session.add(
                ReviewLog(
                    id=_import_id(session, ReviewLog, review.get("id"), taken),
                    card_id=exercise_map[str(card["exercise_id"])],
                    rating=int(review.get("rating") or 0),
                    interval_days=float(review.get("interval_days") or 0),
                    elapsed_days=float(review.get("elapsed_days") or 0),
                    reviewed_at=_parse_datetime(review.get("reviewed_at")) or utcnow(),
                )
            )

    existing_pattern_keys = set(session.scalars(select(ErrorPattern.key)))
    for pattern in bundle.patterns:
        key = str(pattern.get("key") or "").strip()
        if not key or key in existing_pattern_keys:
            continue
        existing_pattern_keys.add(key)
        session.add(
            ErrorPattern(
                key=key[:80],
                course_type_id=course.course_type_id,
                name=str(pattern.get("name") or key)[:200],
                description=str(pattern.get("description") or ""),
                example=pattern.get("example"),
                detection=pattern.get("detection"),
                is_system=False,
                is_active=bool(pattern.get("is_active", True)),
                order_idx=int(pattern.get("order_idx") or 0),
            )
        )

    history = bundle.history
    for attempt in history.get("attempts", []):
        attempt_row = Attempt(
            id=_import_id(session, Attempt, attempt.get("id"), taken),
            activity_id=activity_map[str(attempt["activity_id"])],
            mode=str(attempt.get("mode") or "practice"),
            started_at=_parse_datetime(attempt.get("started_at")) or utcnow(),
            finished_at=_parse_datetime(attempt.get("finished_at")),
            score=attempt.get("score"),
            meta=attempt.get("meta"),
        )
        session.add(attempt_row)
        session.flush()
        attempt_map[str(attempt["id"])] = attempt_row.id
    for answer in history.get("answers", []):
        session.add(
            Answer(
                id=_import_id(session, Answer, answer.get("id"), taken),
                attempt_id=attempt_map[str(answer["attempt_id"])],
                question_id=question_map[str(answer["question_id"])],
                response=answer.get("response"),
                input_mode=answer.get("input_mode"),
                correct=answer.get("correct"),
                partial_credit=answer.get("partial_credit"),
                feedback=answer.get("feedback"),
                graded_by=answer.get("graded_by"),
                time_ms=answer.get("time_ms"),
                retries=int(answer.get("retries") or 0),
                error_tags=answer.get("error_tags"),
                help_events=answer.get("help_events"),
                created_at=_parse_datetime(answer.get("created_at")) or utcnow(),
            )
        )
    for row in history.get("exercise_sessions", []):
        session_row = ExerciseSession(
            id=_import_id(session, ExerciseSession, row.get("id"), taken),
            exercise_id=exercise_map[str(row["exercise_id"])],
            current_step_idx=int(row.get("current_step_idx") or 0),
            status=str(row.get("status") or "active"),
            socratic=bool(row.get("socratic")),
            independence_score=row.get("independence_score"),
            started_at=_parse_datetime(row.get("started_at")) or utcnow(),
            finished_at=_parse_datetime(row.get("finished_at")),
        )
        session.add(session_row)
        session.flush()
        session_map[row["id"]] = session_row.id
    for row in history.get("step_attempts", []):
        session.add(
            StepAttempt(
                id=_import_id(session, StepAttempt, row.get("id"), taken),
                session_id=session_map[str(row["session_id"])],
                step_idx=int(row.get("step_idx") or 0),
                response=row.get("response"),
                correct=row.get("correct"),
                hint_level_used=row.get("hint_level_used"),
                error_class=row.get("error_class"),
                feedback=row.get("feedback"),
                state=row.get("state"),
                created_at=_parse_datetime(row.get("created_at")) or utcnow(),
            )
        )
    for row in history.get("quiz_help_events", []):
        session.add(
            QuizHelpEvent(
                id=_import_id(session, QuizHelpEvent, row.get("id"), taken),
                attempt_id=attempt_map[str(row["attempt_id"])],
                question_id=question_map[str(row["question_id"])],
                level=int(row.get("level") or 0),
                markdown=str(row.get("markdown") or ""),
                violations=row.get("violations"),
                created_at=_parse_datetime(row.get("created_at")) or utcnow(),
            )
        )
    session.flush()

    for entry in bundle.skills:
        skill = session.scalars(select(Skill).where(Skill.name == entry["skill"])).first()
        if skill is None:
            continue
        existing_version = session.scalars(
            select(SkillVersion.version)
            .where(
                SkillVersion.skill_id == skill.id,
                SkillVersion.scope_type == "course",
                SkillVersion.scope_ref == course.id,
            )
            .order_by(SkillVersion.version.desc())
            .limit(1)
        ).first()
        next_version = (existing_version + 1) if existing_version else 2
        session.add(
            SkillVersion(
                skill_id=skill.id,
                scope_type="course",
                scope_ref=course.id,
                version=next_version,
                system_template=entry.get("system_template") or "",
                user_template=entry.get("user_template") or "",
                params=entry.get("params"),
                contract=entry.get("contract"),
                is_active=bool(entry.get("is_active")),
            )
        )

    for entry in bundle.external_sources:
        try:
            provider_raw = str(entry.get("provider") or "").strip() or None
            kind, url, options = validate_external_source(
                str(entry.get("kind") or ""),
                str(entry.get("url") or ""),
                entry.get("options"),
                provider_raw,
            )
        except ExtensionError:
            continue
        session.add(
            ExternalSource(
                profile_id=profile_id,
                course_id=course.id,
                provider=provider_raw or kind,
                kind=kind,
                url=url,
                label=entry.get("label"),
                options=options,
                enabled=bool(entry.get("enabled", True)),
                scan_interval_sec=entry.get("scan_interval_sec"),
            )
        )

    session.commit()
    return {
        "course_id": course.id,
        "title": course.title,
        "imported_at": utcnow().isoformat(),
        "postprocess_job_ids": postprocess_job_ids,
    }
