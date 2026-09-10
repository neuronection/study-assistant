import { useEffect, useRef, useSyncExternalStore } from 'react'

import type { MaterialUploadController } from '@/components/materials/materialUpload'

export interface WindowDropTarget {
  label: string
  upload: () => MaterialUploadController | null
}

interface RegisteredTarget extends WindowDropTarget {
  token: symbol
}

let current: RegisteredTarget | null = null
let version = 0
const listeners = new Set<() => void>()

function emit(): void {
  version += 1
  for (const listener of listeners) {
    listener()
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function setWindowDropTarget(target: WindowDropTarget): void {
  current = { ...target, token: Symbol() }
  emit()
}

export function clearWindowDropTarget(): void {
  current = null
  emit()
}

export function getWindowDropTarget(): WindowDropTarget | null {
  return current
}

export function useWindowDropTarget(): WindowDropTarget | null {
  useSyncExternalStore(subscribe, () => version)
  return current
}

export function useWindowDropRegistration(
  active: boolean,
  label: string,
  getUpload: () => MaterialUploadController | null,
): void {
  const getUploadRef = useRef(getUpload)
  getUploadRef.current = getUpload
  useEffect(() => {
    if (!active) {
      return
    }
    const upload = (): MaterialUploadController | null => getUploadRef.current()
    setWindowDropTarget({ label, upload })
    return () => {
      if (current !== null && current.upload === upload) {
        clearWindowDropTarget()
      }
    }
  }, [active, label])
}
