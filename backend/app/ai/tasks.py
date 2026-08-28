from dataclasses import dataclass


@dataclass(frozen=True)
class TaskDef:
    task: str
    description: str
    requires: str


TASK_DEFS: list[TaskDef] = [
    TaskDef("ocr", "Page & handwriting OCR → markdown (LaTeX for math, tables)", "vision"),
    TaskDef("notes_ocr", "Handwritten notes & answers → markdown blocks", "vision"),
    TaskDef("description", "Material index cards: summary, topics, key terms", "text"),
    TaskDef("outline", "Course outline & material allocation drafts", "text"),
    TaskDef("quizgen", "Quiz question generation", "text"),
    TaskDef("exgen", "Exercise & drill generation (multi-step)", "text"),
    TaskDef("concepts", "Concept extraction & linking from material", "text"),
    TaskDef("tutor", "Guided tutoring & hint ladder", "text"),
    TaskDef("grade", "Answer grading & feedback", "text"),
    TaskDef("chat", "Course-scoped RAG chat", "text"),
    TaskDef("flashcards", "Flashcard generation", "text"),
    TaskDef("embeddings", "Chunk embeddings for semantic search", "embeddings"),
    TaskDef("material_compose", "AI-composed study documents (guides, summaries)", "text"),
    TaskDef(
        "editor_transform",
        "Inline AI text transforms for the rich editor (explain, compact, rewrite…)",
        "text",
    ),
    TaskDef(
        "transcribe",
        "Speech-to-text dictation (Whisper-class models)",
        "audio",
    ),
]

TASKS_BY_NAME = {task_def.task: task_def for task_def in TASK_DEFS}
