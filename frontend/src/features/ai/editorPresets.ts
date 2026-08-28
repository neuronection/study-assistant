import type { LucideIcon } from 'lucide-react'
import {
  Expand,
  FileText,
  HelpCircle,
  Languages,
  List,
  ListTree,
  Minus,
  MessageSquareText,
  PenLine,
  Shrink,
  SpellCheck,
} from 'lucide-react'

export type EditorPresetKey =
  | 'explain'
  | 'answer'
  | 'compact'
  | 'expand'
  | 'rewrite'
  | 'simplify'
  | 'grammar'
  | 'structure'
  | 'bullets'
  | 'markdown'
  | 'translate'

export interface EditorPreset {
  key: EditorPresetKey
  icon: LucideIcon
  labelKey: string
}

export const EDITOR_PRESETS: EditorPreset[] = [
  { key: 'explain', icon: HelpCircle, labelKey: 'editor.ai.explain' },
  { key: 'answer', icon: MessageSquareText, labelKey: 'editor.ai.answer' },
  { key: 'compact', icon: Shrink, labelKey: 'editor.ai.compact' },
  { key: 'expand', icon: Expand, labelKey: 'editor.ai.expand' },
  { key: 'rewrite', icon: PenLine, labelKey: 'editor.ai.rewrite' },
  { key: 'simplify', icon: Minus, labelKey: 'editor.ai.simplify' },
  { key: 'grammar', icon: SpellCheck, labelKey: 'editor.ai.grammar' },
  { key: 'structure', icon: ListTree, labelKey: 'editor.ai.structure' },
  { key: 'bullets', icon: List, labelKey: 'editor.ai.bullets' },
  { key: 'markdown', icon: FileText, labelKey: 'editor.ai.markdown' },
  { key: 'translate', icon: Languages, labelKey: 'editor.ai.translate' },
]

export const PRESET_LABEL_KEYS: Record<EditorPresetKey, string> = Object.fromEntries(
  EDITOR_PRESETS.map((preset) => [preset.key, preset.labelKey])
) as Record<EditorPresetKey, string>