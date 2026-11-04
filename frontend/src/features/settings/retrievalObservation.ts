import type {
  RetrievalQuality,
  RetrievalQueryHealth,
  RetrievalRuns,
  RetrievalSpaces,
} from '@/lib/api'

export const OBSERVATION_SECTIONS = [
  'overview',
  'spaces',
  'runs',
  'quality',
  'query-health',
  'failures',
  'usage',
] as const

export type ObservationSection = (typeof OBSERVATION_SECTIONS)[number]

const SECTION_KEYS: Record<ObservationSection, string> = {
  overview: 'retrievalObsSectionOverview',
  spaces: 'retrievalObsSectionSpaces',
  runs: 'retrievalObsSectionRuns',
  quality: 'retrievalObsSectionQuality',
  'query-health': 'retrievalObsSectionQueryHealth',
  failures: 'retrievalObsSectionFailures',
  usage: 'retrievalObsSectionUsage',
}

export function observationSectionKey(section: ObservationSection): string {
  return `settings.${SECTION_KEYS[section]}`
}

export function parseObservationSection(raw: string | undefined): ObservationSection {
  return (OBSERVATION_SECTIONS as readonly string[]).includes(raw ?? '')
    ? (raw as ObservationSection)
    : 'overview'
}

export const OBSERVATION_WINDOWS = ['24h', '7d', '30d', '90d'] as const
export type ObservationWindow = (typeof OBSERVATION_WINDOWS)[number]

export function parseObservationWindow(raw: string | undefined): ObservationWindow {
  return (OBSERVATION_WINDOWS as readonly string[]).includes(raw ?? '')
    ? (raw as ObservationWindow)
    : '24h'
}

export function observationWindowKey(window: ObservationWindow): string {
  return `settings.retrievalObsWindow${window}`
}

export type RetrievalDetail =
  | { kind: 'run'; id: string }
  | { kind: 'space'; id: string }
  | { kind: 'quality'; id: string }

const DETAIL_PREFIX = {
  space: 'space:',
  quality: 'quality:',
} as const

export function parseRetrievalDetail(raw: string | null | undefined): RetrievalDetail | null {
  if (!raw) return null
  if (raw.startsWith(DETAIL_PREFIX.space)) {
    const id = raw.slice(DETAIL_PREFIX.space.length)
    return id ? { kind: 'space', id } : null
  }
  if (raw.startsWith(DETAIL_PREFIX.quality)) {
    const id = raw.slice(DETAIL_PREFIX.quality.length)
    return id ? { kind: 'quality', id } : null
  }
  return { kind: 'run', id: raw }
}

export function detailParam(detail: RetrievalDetail): string {
  if (detail.kind === 'space') return `${DETAIL_PREFIX.space}${detail.id}`
  if (detail.kind === 'quality') return `${DETAIL_PREFIX.quality}${detail.id}`
  return detail.id
}

export function stateKey(state: string): string {
  if (state === 'ready') return 'retrievalStateReady'
  if (state === 'degraded') return 'retrievalStateDegraded'
  if (state === 'cold') return 'retrievalStateCold'
  return 'retrievalStateEmpty'
}

export function runStatusKey(status: string): string {
  if (status === 'running') return 'retrievalRunRunning'
  if (status === 'succeeded') return 'retrievalRunSucceeded'
  if (status === 'failed') return 'retrievalRunFailed'
  if (status === 'cancelled') return 'retrievalRunCancelled'
  return 'retrievalRunQueued'
}

export function runTypeKey(jobType: string): string {
  if (jobType === 'VECTOR_MAINTENANCE') return 'retrievalRunTypeMaintenance'
  if (jobType === 'VECTOR_CUTOVER') return 'retrievalRunTypeCutover'
  return 'retrievalRunTypeReindex'
}

export function spaceStatusKey(status: string): string {
  return `retrievalSpace${status}`
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value * 100)}%`
}

export function formatRate(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(1)}%`
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value)} ms`
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString()
}

export function shortId(value: string | null | undefined): string {
  if (!value) return '—'
  return value.length > 12 ? value.slice(0, 12) : value
}

export function formatWhen(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString()
}

export function queryHealthReasons(
  health: RetrievalQueryHealth['health'] | null | undefined
): [string, number][] {
  const reasons = health?.degraded_reasons ?? {}
  return Object.entries(reasons)
    .map(([reason, count]) => [reason, Number(count)] as [string, number])
    .sort((left, right) => right[1] - left[1])
}

export function queryHealthViews(
  health: RetrievalQueryHealth['health'] | null | undefined
): [string, number][] {
  const views = health?.per_view_hits ?? {}
  return Object.entries(views)
    .map(([view, count]) => [view, Number(count)] as [string, number])
    .sort((left, right) => right[1] - left[1])
}

export type FailureKind = 'embed_provider' | 'indexing' | 'cutover_gate' | 'maintenance'

export interface FailureGroup {
  id: string
  kind: FailureKind
  reason: string
  count: number
  spaceId: string
  runId: string | null
  lastSeen: string | null
  retryable: boolean
}

type FailureInputs = {
  runs: NonNullable<RetrievalRuns['runs']>
  spaces: NonNullable<RetrievalSpaces['spaces']>
  quality: RetrievalQuality | null
  health: RetrievalQueryHealth | null
}

function groupId(kind: string, spaceId: string, runId: string | null, reason: string) {
  return `${kind}:${spaceId}:${runId ?? 'none'}:${reason}`
}

function runFailureKind(jobType: string): FailureKind {
  if (jobType === 'VECTOR_MAINTENANCE') return 'maintenance'
  if (jobType === 'VECTOR_CUTOVER') return 'cutover_gate'
  return 'indexing'
}

export function collectFailureGroups({
  runs,
  spaces,
  quality,
  health,
}: FailureInputs): FailureGroup[] {
  const groups = new Map<string, FailureGroup>()
  const add = (group: Omit<FailureGroup, 'id'>) => {
    const id = groupId(group.kind, group.spaceId, group.runId, group.reason)
    const existing = groups.get(id)
    if (existing) {
      existing.count += group.count
      if (
        group.lastSeen &&
        (!existing.lastSeen ||
          new Date(group.lastSeen).getTime() > new Date(existing.lastSeen).getTime())
      ) {
        existing.lastSeen = group.lastSeen
      }
      return
    }
    groups.set(id, { ...group, id })
  }

  for (const entry of runs) {
    if (entry.run.status !== 'failed') continue
    const failed = entry.result?.failed ?? 0
    const gateFailed = entry.result?.gate === 'fail'
    add({
      kind: runFailureKind(entry.run.job_type),
      reason: gateFailed ? 'gate_failed' : failed > 0 ? 'embed_failed' : 'run_failed',
      count: Math.max(failed, 1),
      spaceId: entry.run.space_id,
      runId: entry.run.run_id,
      lastSeen:
        entry.run.finished_at ?? entry.run.started_at ?? entry.run.created_at ?? null,
      retryable: true,
    })
  }

  for (const space of spaces) {
    if ((space.failed ?? 0) > 0) {
      add({
        kind: 'indexing',
        reason: 'documents_failed',
        count: space.failed ?? 0,
        spaceId: space.space_id,
        runId: null,
        lastSeen: space.last_reindex_at ?? null,
        retryable: false,
      })
    }
    if (space.quality_state === 'sampled' && space.quality_gate === 'fail') {
      add({
        kind: 'cutover_gate',
        reason: 'quality_gate_failed',
        count: 1,
        spaceId: space.space_id,
        runId: null,
        lastSeen: null,
        retryable: false,
      })
    }
  }

  if (quality?.state === 'sampled' && quality.quality?.passed === false) {
    add({
      kind: 'cutover_gate',
      reason: 'quality_gate_failed',
      count: 1,
      spaceId: quality.space_id,
      runId: quality.compare_run_id ?? null,
      lastSeen: quality.quality.generated_at ?? null,
      retryable: false,
    })
  }

  for (const [reason, count] of queryHealthReasons(health?.health)) {
    const kind: FailureKind =
      reason === 'provider_unassigned' || reason === 'embed_failed'
        ? 'embed_provider'
        : 'indexing'
    add({
      kind,
      reason,
      count,
      spaceId: health?.health.space_id ?? 'unknown',
      runId: null,
      lastSeen: health?.window_end ?? null,
      retryable: false,
    })
  }

  return [...groups.values()].sort((left, right) => right.count - left.count)
}

export const FAILURE_REASON_KEYS: Record<string, string> = {
  run_failed: 'retrievalObsReasonRunFailed',
  gate_failed: 'retrievalObsReasonGateFailed',
  embed_failed: 'retrievalObsReasonEmbedFailed',
  documents_failed: 'retrievalObsReasonDocumentsFailed',
  quality_gate_failed: 'retrievalObsReasonQualityGate',
  provider_unassigned: 'retrievalObsReasonProviderUnassigned',
  index_missing: 'retrievalObsReasonIndexMissing',
  space_mismatch: 'retrievalObsReasonSpaceMismatch',
  over_cap: 'retrievalObsReasonOverCap',
}

export const FAILURE_KIND_KEYS: Record<FailureKind, string> = {
  embed_provider: 'retrievalObsFailureKindEmbedding',
  indexing: 'retrievalObsFailureKindIndexing',
  cutover_gate: 'retrievalObsFailureKindCutoverGate',
  maintenance: 'retrievalObsFailureKindMaintenance',
}

export const USAGE_KIND_KEYS: Record<string, string> = {
  query: 'retrievalObsKindQuery',
  golden_query: 'retrievalObsKindQuery',
  material: 'retrievalObsKindMaterial',
  chunk: 'retrievalObsKindMaterial',
  unattributed: 'retrievalObsKindUnattributed',
  unknown: 'retrievalObsKindUnknown',
}
