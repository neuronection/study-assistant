import { createContext } from 'react'

export interface DrawingOcrDiff {
  before: string
  after: string
}

export interface DrawingDiffStore {
  diffs: ReadonlyMap<string, DrawingOcrDiff>
  dismiss: (drawingId: string) => void
}

export const DrawingDiffContext = createContext<DrawingDiffStore | null>(null)
