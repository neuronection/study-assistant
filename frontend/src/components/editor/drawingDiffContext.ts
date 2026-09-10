import { createContext } from 'react'

export interface DrawingOcrDiff {
  before: string
  after: string
}

export interface DrawingDiffStore {
  diffs: ReadonlyMap<number, DrawingOcrDiff>
  dismiss: (drawingId: number) => void
}

export const DrawingDiffContext = createContext<DrawingDiffStore | null>(null)
