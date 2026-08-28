import type { NodeViewProps } from '@tiptap/core'
import Image from '@tiptap/extension-image'
import { NodeViewWrapper, ReactNodeViewRenderer } from '@tiptap/react'
import { useEffect, useReducer } from 'react'

import { DrawingBlock } from '@/components/editor/DrawingBlock'

export interface DrawingMeta {
  id: number
  png_sha: string | null
  ocr_markdown: string | null
  strokes?: unknown[]
  view?: { x: number; y: number; width: number; height: number } | null
  ocr_version?: number
}

export type DrawingAction = 'edit' | 'reocr' | 'copy' | 'delete'

export type DrawingActionHandler = (id: number, action: DrawingAction) => void

export const DRAWING_SRC_PREFIX = 'ca-drawing://'

export function drawingSrc(id: number): string {
  return `${DRAWING_SRC_PREFIX}${id}`
}

export function parseDrawingSrc(src: string): number | null {
  if (!src.startsWith(DRAWING_SRC_PREFIX)) {
    return null
  }
  const id = Number(src.slice(DRAWING_SRC_PREFIX.length))
  return Number.isInteger(id) && id !== 0 ? id : null
}

export function createDrawingImage(
  resolve: (id: number) => DrawingMeta | undefined,
  onAction: DrawingActionHandler
) {
  const listeners = new Set<() => void>()

  function ImageView({ node, selected }: NodeViewProps) {
    const [, bump] = useReducer((count: number) => count + 1, 0)
    useEffect(() => {
      listeners.add(bump)
      return () => {
        listeners.delete(bump)
      }
    }, [])
    const src = String(node.attrs.src ?? '')
    const drawingId = parseDrawingSrc(src)
    if (drawingId === null) {
      return (
        <NodeViewWrapper>
          <img src={src} alt={String(node.attrs.alt ?? '')} />
        </NodeViewWrapper>
      )
    }
    return (
      <NodeViewWrapper>
        <div className="my-3">
          <DrawingBlock
            drawingId={drawingId}
            meta={resolve(drawingId)}
            onAction={onAction}
            menuVisible={selected === true}
            selected={selected === true}
          />
        </div>
      </NodeViewWrapper>
    )
  }

  const extension = Image.extend({
    draggable: true,
    addNodeView() {
      return ReactNodeViewRenderer(ImageView)
    },
  })
  return {
    extension,
    refresh: () => {
      for (const listener of listeners) {
        listener()
      }
    },
  }
}
