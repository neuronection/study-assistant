from typing import Any

from pydantic import BaseModel, Field

from ..core.vocab import (
    ConceptRelation,
    MaterialKind,
    MaterialStatus,
    ReviewFindingKind,
    StudyStatus,
)


class TreeNodeCounts(BaseModel):
    materials: int = 0
    notes: int = 0
    quizzes: int = 0
    exercises: int = 0
    flashcards: int = 0
    studied: int = 0
    cards_due: int = 0


class TreeNodeMaterialLink(BaseModel):
    material_id: int
    title: str
    rationale: str | None
    auto_assigned: bool
    confidence: float | None


class TreeNodeFolderLink(BaseModel):
    folder_id: int
    name: str
    source_id: int | None


class TreeNodeOut(BaseModel):
    id: int
    title: str
    summary: str | None
    objectives: list[str]
    ai_hint: str | None
    order_idx: int
    depth: int
    is_root: bool
    children: list["TreeNodeOut"]
    counts: TreeNodeCounts
    folder_links: list[TreeNodeFolderLink]
    materials: list[TreeNodeMaterialLink]


TreeNodeOut.model_rebuild()


class NodeCreatedOut(BaseModel):
    id: int
    title: str
    order_idx: int
    depth: int


class NodeDetailOut(BaseModel):
    id: int
    course_id: int
    parent_id: int | None
    title: str
    summary: str | None
    objectives: list[str]
    ai_hint: str | None
    depth: int
    is_root: bool
    order_idx: int


class NodeUpdatedOut(BaseModel):
    id: int
    title: str
    ai_hint: str | None


class NodeMovedOut(BaseModel):
    id: int
    parent_id: int | None
    order_idx: int


class NodeDeletedOut(BaseModel):
    undo_token: str | None


class NodeRestoredOut(BaseModel):
    id: int


class FolderAssignedOut(BaseModel):
    node_id: int
    folder_id: int


class StudyStateOut(BaseModel):
    status: str
    progress: float
    last_opened_at: str | None


class NodeConceptLinkedOut(BaseModel):
    node_id: int
    concept_id: int


class MaterialAssignedOut(BaseModel):
    node_id: int
    material_id: int


class ViaFolderOut(BaseModel):
    id: int
    name: str


class CourseMaterialsEntryOut(BaseModel):
    node_id: int
    node_title: str
    node_is_root: bool
    material_id: int
    title: str
    rationale: str | None
    auto_assigned: bool
    confidence: float | None
    via_folder: ViaFolderOut | None


class CourseDeletedOut(BaseModel):
    status: str
    course_id: int


class BundlePreviewOut(BaseModel):
    title: str | None
    counts: dict[str, int]
    warnings: list[str]


class ImportedCourseOut(BaseModel):
    course_id: int
    title: str
    imported_at: str
    postprocess_job_ids: list[int] = []


class CourseImportOut(BaseModel):
    dry_run: bool
    preview: BundlePreviewOut | None = None
    imported: ImportedCourseOut | None = None


class OutlineSectionOut(BaseModel):
    title: str
    objectives: list[str]
    material_ids: list[int]
    rationale: str | None
    confidence: float


class OutlineChapterOut(BaseModel):
    title: str
    summary: str | None
    sections: list[OutlineSectionOut]


class OutlineDraftOut(BaseModel):
    chapters: list[OutlineChapterOut]


class OutlineCommitOut(BaseModel):
    chapters: int
    sections: int
    allocations: int


class ConceptDraftEntryOut(BaseModel):
    name: str
    description: str | None
    aliases: list[str]


class ConceptLinkDraftOut(BaseModel):
    source: str = Field(serialization_alias="from", validation_alias="from")
    target: str = Field(serialization_alias="to", validation_alias="to")
    relation: ConceptRelation


class ConceptNodeDraftOut(BaseModel):
    node_title: str
    concepts: list[str]


class ConceptDraftOut(BaseModel):
    concepts: list[ConceptDraftEntryOut]
    links: list[ConceptLinkDraftOut]
    nodes: list[ConceptNodeDraftOut]


class ConceptsCommitOut(BaseModel):
    concepts: int
    created: int
    links: int
    nodes: int


class ConceptCoverageOut(BaseModel):
    node_id: int
    node_title: str


class ConceptGraphConceptOut(BaseModel):
    id: int
    name: str
    description: str | None
    aliases: list[str]
    nodes: list[ConceptCoverageOut]


class ConceptGraphLinkOut(BaseModel):
    source: str | None = Field(serialization_alias="from", validation_alias="from")
    target: str | None = Field(serialization_alias="to", validation_alias="to")
    relation: ConceptRelation


class ConceptGraphOut(BaseModel):
    concepts: list[ConceptGraphConceptOut]
    links: list[ConceptGraphLinkOut]


class BreadcrumbEntryOut(BaseModel):
    id: int
    title: str
    depth: int


class WorkspaceNodeOut(BaseModel):
    id: int
    course_id: int
    course_title: str | None
    title: str
    summary: str | None
    objectives: list[str]
    ai_hint: str | None
    depth: int
    is_root: bool
    parent_id: int | None
    breadcrumb: list[BreadcrumbEntryOut]


class WorkspaceChildOut(BaseModel):
    id: int
    title: str
    depth: int
    order_idx: int
    objectives: list[str]
    summary: str | None


class WorkspaceFolderOut(BaseModel):
    folder_id: int
    name: str
    source_id: int | None
    member_count: int
    rationale: str | None
    auto_assigned: bool


class WorkspaceMaterialOut(BaseModel):
    material_id: int
    title: str
    kind: MaterialKind
    status: MaterialStatus
    read_status: StudyStatus
    progress: float
    rationale: str | None
    auto_assigned: bool | None
    confidence: float | None
    provenance: dict[str, Any] | None
    has_extraction: bool
    via_folder_id: int | None
    via_folder_name: str | None


class WorkspaceNoteOut(BaseModel):
    id: int
    title: str
    node_id: int | None
    owner_type: str | None
    owner_id: int | None
    pinned: bool
    updated_at: str | None


class ScopeCountsOut(BaseModel):
    direct: int
    with_children: int


class WorkspaceCountsOut(BaseModel):
    notes: ScopeCountsOut
    quizzes: ScopeCountsOut
    exercises: ScopeCountsOut
    flashcards: ScopeCountsOut
    child_nodes: int


class WorkspaceConceptOut(BaseModel):
    id: int
    name: str
    direct: bool
    node_ids: list[int]


class NodeWorkspaceOut(BaseModel):
    node: WorkspaceNodeOut
    children: list[WorkspaceChildOut]
    folders: list[WorkspaceFolderOut]
    materials: list[WorkspaceMaterialOut]
    folder_material_ids: list[int]
    child_materials: dict[str, list[WorkspaceMaterialOut]]
    notes: list[WorkspaceNoteOut]
    counts: WorkspaceCountsOut
    concepts: list[WorkspaceConceptOut]


class ReviewFindingOut(BaseModel):
    kind: ReviewFindingKind
    title: str
    detail: str | None
    suggestion: str | None


class NodeReviewOut(BaseModel):
    node_id: int
    node_title: str
    findings: list[ReviewFindingOut]
    material_id: int


class DraftNoteOut(BaseModel):
    note_id: int
    markdown: str
    existing: bool


class ArtifactRefOut(BaseModel):
    material_id: int
    title: str


class NodeArtifactsOut(BaseModel):
    cheat_sheet: ArtifactRefOut | None
    reviews: list[ArtifactRefOut]
    artifact: ArtifactRefOut | None = None
