from enum import StrEnum


class StrVocab(StrEnum):
    @classmethod
    def parse(cls, value: str) -> "StrVocab":
        try:
            return cls(value)
        except ValueError:
            allowed = ", ".join(m.value for m in cls)
            raise ValueError(f"unknown {cls.__name__} '{value}' (allowed: {allowed})") from None


class JobStatus(StrVocab):
    QUEUED = "queued"
    RUNNING = "running"
    FAILED = "failed"
    DONE = "done"
    CANCELLED = "cancelled"

    @classmethod
    def active(cls) -> tuple["JobStatus", "JobStatus"]:
        return (cls.QUEUED, cls.RUNNING)


class JobType(StrVocab):
    INGEST = "ingest"
    POSTPROCESS = "postprocess"
    CHAT_TURN = "chat_turn"
    DRAWING_OCR = "drawing_ocr"
    IMAGE_OCR = "image_ocr"


class ChatEngine(StrVocab):
    LEGACY = "legacy"
    GRAPH = "graph"


class MaterialKind(StrVocab):
    PDF = "pdf"
    IMAGE = "image"
    MD = "md"
    TXT = "txt"
    DOC = "doc"
    DOCX = "docx"
    PPTX = "pptx"
    EPUB = "epub"
    HTML = "html"
    AUDIO = "audio"
    VIDEO = "video"


class MaterialStatus(StrVocab):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    MISSING = "missing"


class AttemptMode(StrVocab):
    PRACTICE = "practice"
    EXAM = "exam"


class ComposeKind(StrVocab):
    STUDY_GUIDE = "study_guide"
    SUMMARY_SHEET = "summary_sheet"
    PRACTICE_SET = "practice_set"
    ERROR_RECAP = "error_recap"
    MINDMAP = "mindmap"
    FORMULA_SHEET = "formula_sheet"
    CHEAT_SHEET = "cheat_sheet"
    NODE_REVIEW = "node_review"


class Capability(StrVocab):
    TEXT = "text"
    VISION = "vision"
    EMBEDDINGS = "embeddings"
    AUDIO = "audio"


class ProvenanceKind(StrVocab):
    AI_COMPOSED = "ai-composed"
    DERIVED = "derived"
    CONVERTED = "converted"
    TRANSCRIBED = "transcribed"


class ConceptRelation(StrVocab):
    PREREQ_OF = "prereq-of"
    PART_OF = "part-of"
    RELATED_TO = "related-to"


class ReviewFindingKind(StrVocab):
    GAP = "gap"
    ORDERING = "ordering"
    ORPHAN = "orphan"
    COVERAGE = "coverage"


class StudyStatus(StrVocab):
    UNREAD = "unread"
    READING = "reading"
    STUDIED = "studied"


class RecommendationKind(StrVocab):
    REVIEW = "review"
    READ = "read"
    DRILL = "drill"
    CHALLENGE = "challenge"


class SpeedLabel(StrVocab):
    RUSHING = "rushing"
    SLOW = "slow"
    NORMAL = "normal"


class SpeedQuadrant(StrVocab):
    FLUENT = "fluent"
    RUSHING = "rushing"
    EFFORTFUL = "effortful"
    STRUGGLING = "struggling"


class ItemFlag(StrVocab):
    OK = "ok"
    REVIEW = "review"
    ELO_OUTLIER = "elo_outlier"


class WsTopic:
    @staticmethod
    def jobs(job_id: int) -> str:
        return f"jobs:{job_id}"

    @staticmethod
    def chat(session_id: int) -> str:
        return f"chat:{session_id}"

    @staticmethod
    def source(source_id: int) -> str:
        return f"source:{source_id}"

    @staticmethod
    def note(note_id: int) -> str:
        return f"note:{note_id}"

    @staticmethod
    def material(material_id: int) -> str:
        return f"material:{material_id}"
