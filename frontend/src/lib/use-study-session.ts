import { useEffect, useRef } from 'react'

import {
  beatStudySession,
  startStudySession,
  type StudySessionKind,
} from '@/lib/api'

const HEARTBEAT_MS = 60_000

export interface StudySessionOptions {
  kind: StudySessionKind
  entityRef?: string | null
  courseId?: number | null
  nodeId?: number | null
  enabled?: boolean
}

/**
 * Opens a `source=auto` study session while the calling surface is mounted
 * and heartbeats it every minute. The backend resumes a matching session
 * ended within its resume window, so param-driven remounts (drawer
 * open/close, tab churn, StrictMode double-effects) fold into one row.
 * Tracking failures never break the surface.
 */
export function useStudySession(options: StudySessionOptions): void {
  const { kind, entityRef = null, courseId = null, nodeId = null, enabled = true } = options
  const latest = useRef({ courseId, nodeId })
  latest.current = { courseId, nodeId }

  useEffect(() => {
    if (!enabled) {
      return
    }
    let sessionId: number | null = null
    let cancelled = false
    startStudySession({
      kind,
      source: 'auto',
      entity_ref: entityRef,
      course_id: latest.current.courseId,
      node_id: latest.current.nodeId,
    })
      .then((row) => {
        if (cancelled) {
          void beatStudySession(row.id, 'end').catch(() => {})
          return
        }
        sessionId = row.id
      })
      .catch(() => {})
    const heartbeat = window.setInterval(() => {
      if (sessionId === null) {
        return
      }
      void beatStudySession(sessionId, 'heartbeat').catch(() => {})
    }, HEARTBEAT_MS)
    return () => {
      cancelled = true
      window.clearInterval(heartbeat)
      if (sessionId !== null) {
        void beatStudySession(sessionId, 'end').catch(() => {})
      }
    }
  }, [kind, entityRef, enabled])
}
