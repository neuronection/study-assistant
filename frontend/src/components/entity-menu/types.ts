import type { LucideIcon } from 'lucide-react'

export interface EntityNode {
  id: string
  label: string
}

export interface EntityContext {
  courseId: number
  scopeNodeId: number | null
}

export interface NodeSource<TNode = unknown> {
  kind: string
  toEntity(node: TNode): EntityNode
  toContext(node: TNode): EntityContext
  llmHint?(node: TNode): string | null
  canAiEdit?: boolean
  canEdit?: boolean
  edit?(node: TNode, label: string): void | Promise<void>
  canRemove?: boolean
  remove?(node: TNode): void | Promise<void>
  canAddChild?: boolean
  addChild?(node: TNode, label: string): void | Promise<void>
}

export interface EntityAction {
  key: string
  icon: LucideIcon
  label: string
  danger?: boolean
  onSelect: () => void
}

export interface EntityActionGroup {
  label?: string
  actions: EntityAction[]
}

export type GenerateTask = 'quiz' | 'exercise' | 'flashcards' | 'study_guide'

export interface EntityActionHandlers {
  ask(entity: EntityNode, context: EntityContext, hint: string | null): void
  generate(
    task: GenerateTask,
    entity: EntityNode,
    context: EntityContext,
    hint: string | null
  ): void
  writeNote(entity: EntityNode, context: EntityContext, hint: string | null): void
  aiEdit?(entity: EntityNode, context: EntityContext): void
  addNote(entity: EntityNode, context: EntityContext): void
  addAsSection?(entity: EntityNode, context: EntityContext): void
  editNode?(): void
  addChild?(): void
  removeNode?(): void
}
