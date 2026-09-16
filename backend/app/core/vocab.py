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
    GENESIS = "genesis"
    URL_IMPORT = "url_import"


class FlowEvent(StrVocab):
    FLOW_STARTED = "flow_started"
    NODE_STARTED = "node_started"
    NODE_FINISHED = "node_finished"
    DELTA = "delta"
    INTERRUPT = "interrupt"
    FLOW_FINISHED = "flow_finished"
    FLOW_FAILED = "flow_failed"


class DiscoveryKind(StrVocab):
    VIDEO = "video"
    COURSE = "course"
    ARTICLE = "article"
    EXERCISE = "exercise"
    OTHER = "other"


class SuggestionStatus(StrVocab):
    SUGGESTED = "suggested"
    SAVED = "saved"
    DISMISSED = "dismissed"


class ExternalSourceKind(StrVocab):
    RSS = "rss"
    YOUTUBE_CHANNEL = "youtube_channel"
    YOUTUBE_PLAYLIST = "youtube_playlist"
    SITE_SEARCH = "site_search"


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
    LINK = "link"


class MaterialStatus(StrVocab):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    MISSING = "missing"


class ExtractionMode(StrVocab):
    AUTO = "auto"
    TEXT = "text"
    OCR = "ocr"


EXTRACTION_MODES: tuple[str, ...] = tuple(mode.value for mode in ExtractionMode)


def applicable_extraction_modes(kind: MaterialKind) -> tuple[ExtractionMode, ...]:
    if kind == MaterialKind.PDF:
        return (ExtractionMode.AUTO, ExtractionMode.TEXT, ExtractionMode.OCR)
    if kind == MaterialKind.IMAGE:
        return (ExtractionMode.AUTO, ExtractionMode.OCR)
    return (ExtractionMode.AUTO,)


class AttemptMode(StrVocab):
    PRACTICE = "practice"
    EXAM = "exam"


class StudySessionKind(StrVocab):
    FOCUS = "focus"
    QUIZ = "quiz"
    EXERCISE = "exercise"
    REVIEW = "review"
    READ = "read"
    NOTE = "note"


class StudySessionSource(StrVocab):
    TIMER = "timer"
    AUTO = "auto"
    MANUAL = "manual"


class GoalUnit(StrVocab):
    ANSWERS = "answers"
    MINUTES = "minutes"


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
    SPEECH = "speech"


class DeriveOutcome(StrVocab):
    CREATED = "created"
    DEDUPED = "deduped"
    SKIPPED = "skipped"


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
    TEACHBACK = "teachback"


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


class CourseOrigin(StrVocab):
    MANUAL = "manual"
    GENESIS = "genesis"
    IMPORT = "import"
    SCRATCH = "scratch"


class PlanItemKind(StrVocab):
    STUDY = "study"
    PRACTICE = "practice"
    REVIEW = "review"
    MILESTONE = "milestone"


PLAN_ITEM_KINDS: tuple[str, ...] = tuple(
    kind.value for kind in PlanItemKind
)


class PlanItemOrigin(StrVocab):
    MANUAL = "manual"
    DRAFT = "draft"


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
    def externalsource(source_id: int) -> str:
        return f"externalsource:{source_id}"

    @staticmethod
    def note(note_id: int) -> str:
        return f"note:{note_id}"

    @staticmethod
    def material(material_id: int) -> str:
        return f"material:{material_id}"


QUESTION_TYPES: tuple[str, ...] = (
    "single",
    "multi",
    "truefalse",
    "text",
    "numeric",
    "equation",
    "numberline",
    "table_fill",
    "composite",
    "graph_read",
    "code",
)
