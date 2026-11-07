import type { components } from '@/lib/api-schema'

type Schemas = components['schemas']

/** Client-side-only shapes (plan 82 B, ADR-203).
 *
 * Every wire shape in `lib/api/*` comes from the generated `api-schema`.
 * The declarations below exist only where the wire is genuinely open and a
 * component needs a narrowed view of it; `HAND_TYPE_REGISTER` is the
 * exhaustive exception list the `check-api-types` gate enforces.
 */

export interface ExerciseOrderingItem {
  id: number
  label: string
}

/** Client request composition shared by the generate endpoints (the wire
 * bodies are the per-endpoint `*GenerateIn` schemas; this mixin keeps one
 * app-side shape for the shared context knobs). */
export type GenerateScope = 'node' | 'subtree' | 'course'

export interface GenerateContext {
  scope?: GenerateScope
  include_material_ids?: string[]
  exclude_material_ids?: string[]
  note_ids?: string[]
  concept_ids?: string[]
  context_hint?: string | null
}

/** Read model of the open `PreviewOut.stats` map (counts + rendered lists). */
export interface AiContextStats {
  materials: { id: string; title: string }[]
  chunks: { material_id: string; title: string }[]
  notes: { id: string; title: string }[]
  concepts: { id: string; name: string }[]
  hints: number
  approx_chars: number
  retrieval_query: string | null
}

/** Identity rows served by the family `nx_auth` kit, which publishes no
 * response models (its admin/me/sessions routes return plain dicts), so the
 * generated schema cannot express them. Registered exceptions, not fakes. */
export interface PublicUser {
  id: string
  email: string
  full_name: string
  is_admin: boolean
  is_active: boolean
}

export interface AdminUser extends PublicUser {
  created_at: string
  activity_count: number
}

export type AdminUserPatch = Schemas['AdminUserUpdateIn']

export interface UserSession {
  id: string
  client_label: string
  created_at: string | null
  expires_at: string
  revoked_at: string | null
  current: boolean
}

/** Desktop-only folder listing (the desktop routes are not in the web
 * OpenAPI export, so no schema exists). */
export interface DesktopFileEntry {
  path: string
  rel: string
  size: number
  mtime: number
}

export interface DesktopFolderListing {
  path: string
  files: DesktopFileEntry[]
}

/** Search-provider catalog (extension-owned, served as an open document). */
export interface SearchProviderCatalogField {
  id: string
  label: string
  required: boolean
  placeholder?: string
  type?: 'text' | 'number'
  advanced?: boolean
  hint?: string | null
}

export interface SearchProviderCatalogEntry {
  label: string
  requiresKey: boolean
  keyUrl: string | null
  baseUrl: string | null
  baseUrlRequired: boolean
  baseUrlHint?: string
  notes?: string | null
  hosting?: 'cloud' | 'self-hosted'
  fields?: SearchProviderCatalogField[]
}

export interface SearchProviderCatalog {
  providerOrder: string[]
  providers: Record<string, SearchProviderCatalogEntry>
  limits: {
    maxResults: { default: number; min: number; max: number }
    timeoutMs: { default: number; min: number; max: number }
  }
}

/** Structured 4xx detail from the provider-setup endpoint. */
export interface ProviderSetupErrorDetail {
  code: string
  suspected_vendor: string | null
  detail: string
}

/** Structured 4xx detail for an unsupported upload suffix. */
export interface UnsupportedTypeDetail {
  reason: 'unsupported_type'
  suffix: string
  accepted: string[]
}

/** Client request vocabulary for external sources (the wire field is a
 * length-bounded string, validated server-side against the registry). */
export type ExternalSourceKind =
  | 'rss'
  | 'youtube_channel'
  | 'youtube_playlist'
  | 'site_search'
  | 'webdav_folder'
  | 'cloud_folder'
  | 'zotero_collection'
  | 'anki_deck'

/** A configured MCP server's tool row (list endpoint returns the raw row). */
export interface McpServerToolInfo {
  name: string
  description: string
  enabled: boolean
  contract: string
  url_pattern: string | null
}

/** The app's read model of a canonical content block (the wire column is
 * an open document by design — ADR-200 keeps block content extensible). */
export interface BlockDto {
  type: string
  md?: string
  [key: string]: unknown
}

/** Upload-time drawing placeholder (client refs before the server mints ids). */
export interface PendingDrawing {
  ref: number | string
  strokes: unknown[]
  png_base64: string
  ocr: boolean
  view?: { x: number; y: number; width: number; height: number } | null
}

/** Client-side edit state for the text-file compose dialog. */
export interface TextFileEditState {
  materialId: string
  content: string
  refToReal: Record<number, string>
  jobId: string | null
}

/** Narrowed view of `StepOut.input` / `QuestionOut.input` widget payloads
 * (the wire field is an open map; each widget family reads its own keys). */
export interface ExerciseStepInput {
  widget:
    | 'matching'
    | 'ordering'
    | 'categorize'
    | 'fill_blank'
    | 'math'
    | 'essay'
    | 'lines'
    | 'numberline'
  kind?: string
  lefts?: string[]
  rights?: { index: number; label: string }[]
  items?: unknown[]
  categories?: string[]
  prompt_md?: string
  blank_count?: number
  lines?: string[]
  requires_fix?: boolean
  min?: number
  max?: number
}

/** Narrowed view of `QuestionOut.input` for the widget families the quiz
 * runner renders (the wire field is an open map by design). */
export interface QuizQuestionInput {
  widget: string
  min?: number
  max?: number
  kind?: string
  lefts?: string[]
  rights?: { index: number; label: string }[]
  items?: unknown[]
  prompt_md?: string
  blank_count?: number
  headers?: string[]
  row_labels?: string[]
  cells?: QuizQuestionCell[][]
  parts?: QuizQuestionPart[]
  starter_code?: string
  tests?: QuizQuestionTest[]
  mode?: string
}

export interface QuizQuestionCell {
  kind: string
  text?: string
}

export interface QuizQuestionPart {
  type: string
}

export interface QuizQuestionTest {
  call: string
  expected?: unknown
  expected_stdout?: string | null
}

/** Narrowed view of a chat tool call's open `quiz` map (the wire type is
 * `Record<string, unknown>` — the backend keeps it open for tool results). */
export interface ToolCallQuizView {
  question?: string
  choices?: string[] | null
  answered?: boolean
  verdict?: string | null
  verdict_detail?: string | null
  student_answer?: string | null
  expected_display?: string | null
}

/** Narrowed view of the persisted turn-failure marker in
 * `chat_messages.state` (an open widget-state document). */
export interface MessageTurnFailureView {
  code: string
  detail: string
}

export const HAND_TYPE_REGISTER = [
  { name: 'AiContextStats', source: 'read model of the open PreviewOut.stats map' },
  { name: 'AdminUser', source: 'nx_auth kit route payload (kit publishes no response model)' },
  { name: 'BlockDto', source: 'read model of an open content block document' },
  { name: 'ComposeKind', source: 'client-side compose-kind list (request vocabulary)' },
  { name: 'ExerciseOrderingItem', source: 'exercise-struct position index', numericId: true },
  { name: 'PendingDrawing', source: 'client placeholder refs', numericId: true },
  { name: 'GenerateContext', source: 'client request composition over the generate endpoints' },
  { name: 'GenerateScope', source: 'client request composition over the generate endpoints' },
  { name: 'ExerciseStepInput', source: 'narrowed view of StepOut.input (open widget map)' },
  { name: 'PublicUser', source: 'nx_auth kit route payload (kit publishes no response model)' },
  { name: 'QuizQuestionInput', source: 'narrowed view of QuestionOut.input (open widget map)' },
  { name: 'QuizQuestionCell', source: 'narrowed view of QuestionOut.input (open widget map)' },
  { name: 'QuizQuestionPart', source: 'narrowed view of QuestionOut.input (open widget map)' },
  { name: 'QuizQuestionTest', source: 'narrowed view of QuestionOut.input (open widget map)' },
  { name: 'TextFileEditState', source: 'client-only text-file edit state' },
  { name: 'ToolCallQuizView', source: 'narrowed view of ToolCallOut.quiz (open wire map)' },
  { name: 'UserSession', source: 'nx_auth kit route payload (kit publishes no response model)' },
  { name: 'DesktopFileEntry', source: 'desktop-only route payload (not in the web OpenAPI export)' },
  { name: 'DesktopFolderListing', source: 'desktop-only route payload (not in the web OpenAPI export)' },
  { name: 'ExternalSourceKind', source: 'client request vocabulary (server validates the registry)' },
  { name: 'McpServerToolInfo', source: 'MCP server tool row (list endpoint returns the raw row)' },
  { name: 'ProviderSetupErrorDetail', source: 'structured 4xx detail (provider setup)' },
  { name: 'SearchProviderCatalog', source: 'extension-owned catalog document (open map)' },
  { name: 'SearchProviderCatalogEntry', source: 'extension-owned catalog document (open map)' },
  { name: 'SearchProviderCatalogField', source: 'extension-owned catalog document (open map)' },
  { name: 'UnsupportedTypeDetail', source: 'structured 4xx detail (upload suffix guard)' },
  { name: 'MessageTurnFailureView', source: 'narrowed view of MessageOut.state.turn_failed (open widget state)' },
] as const

export function toolCallQuiz(quiz: Record<string, unknown> | null | undefined): ToolCallQuizView | null {
  if (quiz === null || quiz === undefined) {
    return null
  }
  const question = quiz.question
  if (typeof question !== 'string' || !question) {
    return null
  }
  const choices = Array.isArray(quiz.choices)
    ? quiz.choices.filter((choice): choice is string => typeof choice === 'string')
    : null
  return {
    question,
    choices,
    answered: quiz.answered === true,
    verdict: typeof quiz.verdict === 'string' ? quiz.verdict : null,
    verdict_detail: typeof quiz.verdict_detail === 'string' ? quiz.verdict_detail : null,
    student_answer: typeof quiz.student_answer === 'string' ? quiz.student_answer : null,
    expected_display:
      typeof quiz.expected_display === 'string' ? quiz.expected_display : null,
  }
}

export function messageTurnFailure(
  state: Record<string, unknown> | null | undefined
): MessageTurnFailureView | null {
  const marker = state?.turn_failed
  if (marker === null || typeof marker !== 'object') {
    return null
  }
  const record = marker as Record<string, unknown>
  if (typeof record.code !== 'string' || typeof record.detail !== 'string') {
    return null
  }
  return { code: record.code, detail: record.detail }
}
