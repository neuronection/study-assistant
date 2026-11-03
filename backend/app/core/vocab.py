from enum import StrEnum


class StrVocab(StrEnum):
    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

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


class DegradedReason(StrVocab):
    """Structured lexical-fallback reason (family retrieval contract)."""

    PROVIDER_UNASSIGNED = "provider_unassigned"
    EMBED_FAILED = "embed_failed"
    INDEX_MISSING = "index_missing"
    SPACE_MISMATCH = "space_mismatch"
    OVER_CAP = "over_cap"


class JobType(StrVocab):
    INGEST = "ingest"
    POSTPROCESS = "postprocess"
    CHAT_TURN = "chat_turn"
    DRAWING_OCR = "drawing_ocr"
    IMAGE_OCR = "image_ocr"
    GENESIS = "genesis"
    URL_IMPORT = "url_import"
    COMPOSE = "compose"
    # Family retrieval-operations contract (plan 51 Q0): the names are the
    # exact `retrieval_ops.VECTOR_JOB_TYPES` tokens, uppercase by contract.
    VECTOR_REINDEX = "VECTOR_REINDEX"
    VECTOR_MAINTENANCE = "VECTOR_MAINTENANCE"
    VECTOR_CUTOVER = "VECTOR_CUTOVER"


class QuestionType(StrVocab):
    SINGLE = "single"
    MULTI = "multi"
    TRUEFALSE = "truefalse"
    TEXT = "text"
    NUMERIC = "numeric"
    EQUATION = "equation"
    NUMBERLINE = "numberline"
    TABLE_FILL = "table_fill"
    COMPOSITE = "composite"
    GRAPH_READ = "graph_read"
    CODE = "code"
    MATCHING = "matching"
    ORDERING = "ordering"
    CLOZE = "cloze"
    ESSAY = "essay"


class ExerciseKind(StrVocab):
    MULTI_STEP = "multi_step"
    CARD_BASIC = "card_basic"
    CARD_REVERSE = "card_reverse"
    CARD_CLOZE = "card_cloze"
    MATCHING = "matching"
    ORDERING = "ordering"
    CATEGORIZE = "categorize"
    FILL_BLANK = "fill_blank"
    EXPLAIN = "explain"
    ERROR_SPOT = "error_spot"
    CORRECT_SOLUTION = "correct_solution"


class FlashcardKind(StrVocab):
    CARD_BASIC = "card_basic"
    CARD_CLOZE = "card_cloze"
    CARD_REVERSE = "card_reverse"


class ToolEntryKind(StrVocab):
    TOOL = "tool"
    CAPABILITY = "capability"


class McpTransport(StrVocab):
    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"


class ChatProposalStatus(StrVocab):
    PROPOSED = "proposed"
    APPROVED = "approved"
    DISMISSED = "dismissed"
    EXECUTED = "executed"
    STALE = "stale"
    CONFLICT = "conflict"

    @classmethod
    def resolvable(cls) -> tuple["ChatProposalStatus", ...]:
        return (cls.PROPOSED, cls.CONFLICT)

    @classmethod
    def resolved(cls) -> tuple["ChatProposalStatus", ...]:
        return (cls.APPROVED, cls.DISMISSED, cls.EXECUTED, cls.STALE, cls.CONFLICT)


class ProposalTargetKind(StrVocab):
    NOTE = "note"
    MATERIAL = "material"
    CONCEPT = "concept"
    LINK = "link"


class ProposalAnchorOp(StrVocab):
    REPLACE = "replace"
    APPEND = "append"
    PREPEND = "prepend"


class QuizVerdict(StrVocab):
    CORRECT = "correct"
    INCORRECT = "incorrect"


class DiscoveryKind(StrVocab):
    VIDEO = "video"
    COURSE = "course"
    ARTICLE = "article"
    EXERCISE = "exercise"
    PAPER = "paper"
    DATASET = "dataset"
    REFERENCE = "reference"
    OTHER = "other"


class CitationKind(StrVocab):
    ARTICLE = "article"
    BOOK = "book"
    CHAPTER = "chapter"
    CONFERENCE = "conference"
    PREPRINT = "preprint"
    THESIS = "thesis"
    REPORT = "report"
    DATASET = "dataset"
    OTHER = "other"


class BibliographyFormat(StrVocab):
    BIBTEX = "bibtex"
    RIS = "ris"


class SuggestionStatus(StrVocab):
    SUGGESTED = "suggested"
    SAVED = "saved"
    DISMISSED = "dismissed"


class ExternalSourceKind(StrVocab):
    RSS = "rss"
    YOUTUBE_CHANNEL = "youtube_channel"
    YOUTUBE_PLAYLIST = "youtube_playlist"
    SITE_SEARCH = "site_search"
    WEBDAV_FOLDER = "webdav_folder"
    CLOUD_FOLDER = "cloud_folder"
    ZOTERO_COLLECTION = "zotero_collection"
    ANKI_DECK = "anki_deck"


class AuthKind(StrVocab):
    TOKEN = "token"
    OAUTH2 = "oauth2"
    NONE = "none"


class SourcePreset(StrVocab):
    FOLDER = "folder"
    VAULT = "vault"


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
    STT = "stt"
    TTS = "tts"
    DECISION = "decision"


class DecisionCapability(StrVocab):
    TOOL_DISPATCH = "tool-dispatch"
    BOOLEAN_GATE = "boolean-gate"
    CHOICE = "choice"
    SCORE = "score"
    OPEN_ARGS = "open-args"


class DecisionTransport(StrVocab):
    SYSTEMONE = "systemone"


class SystemOneErrorKind(StrVocab):
    AUTH = "auth"
    RATE_LIMIT = "rate-limit"
    OVERLOADED = "overloaded"
    VALIDATION = "validation"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


class ProviderErrorCode(StrVocab):
    INVALID_KEY = "invalid_key"
    INSUFFICIENT_CREDIT = "insufficient_credit"
    NEW_USER_QUOTA = "new_user_quota"
    REGION_UNAVAILABLE = "region_unavailable"
    TIMEOUT = "timeout"
    LOCAL_NOT_RUNNING = "local_not_running"
    UNKNOWN = "unknown"


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


class AnalyticsExportFormat(StrVocab):
    CSV = "csv"
    JSON = "json"


class PreprocessMode(StrVocab):
    AUTO = "auto"
    OFF = "off"


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
    EXAM = "exam"
    DEADLINE = "deadline"


PLAN_ITEM_KINDS: tuple[str, ...] = tuple(kind.value for kind in PlanItemKind)


class PlanItemOrigin(StrVocab):
    MANUAL = "manual"
    DRAFT = "draft"
    CALENDAR = "calendar"


class CalendarDirection(StrVocab):
    """How a calendar link moves data (ADR-0052 §6)."""

    PUSH = "push"
    PULL = "pull"
    TWO_WAY = "two-way"


class CalendarStatus(StrVocab):
    """Account/sync state; the family vocabulary plus the two auth states."""

    OK = "ok"
    DEGRADED = "degraded"
    FAILING = "failing"
    STALE = "stale"
    NEEDS_AUTH = "needs-auth"
    NEEDS_SECRET = "needs-secret"


class WsTopic:
    @staticmethod
    def jobs(job_id: str) -> str:
        return f"jobs:{job_id}"

    @staticmethod
    def chat(session_id: str) -> str:
        return f"chat:{session_id}"

    @staticmethod
    def source(source_id: str) -> str:
        return f"source:{source_id}"

    @staticmethod
    def externalsource(source_id: str) -> str:
        return f"externalsource:{source_id}"

    @staticmethod
    def note(note_id: str) -> str:
        return f"note:{note_id}"

    @staticmethod
    def material(material_id: str) -> str:
        return f"material:{material_id}"

    @staticmethod
    def inbox() -> str:
        return "inbox"
