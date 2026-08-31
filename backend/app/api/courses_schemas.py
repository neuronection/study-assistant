from pydantic import BaseModel


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
