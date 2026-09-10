import { ApiError, transcribeAudio } from '@/lib/api'

export const transcribeViaGateway = (audio: Blob) => transcribeAudio(audio)

export const classifyDictationError = (error: unknown) => {
  if (error instanceof ApiError && error.status === 409) {
    return { kind: 'unassigned' as const }
  }
  return {
    kind: 'failed' as const,
    detail: error instanceof Error ? error.message : String(error),
  }
}
