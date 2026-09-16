export interface ShortcutEntry {
  id: string
  keys: string
}

export interface ShortcutGroup {
  id: string
  entries: ShortcutEntry[]
}

export const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    id: 'general',
    entries: [
      { id: 'palette', keys: 'Ctrl+K' },
      { id: 'capture', keys: 'Ctrl+Shift+K' },
      { id: 'help', keys: '?' },
    ],
  },
  {
    id: 'review',
    entries: [
      { id: 'reveal', keys: 'Space' },
      { id: 'rate', keys: '1–4' },
    ],
  },
  {
    id: 'library',
    entries: [
      { id: 'open', keys: 'Enter' },
      { id: 'selection', keys: 'Ctrl+Click' },
      { id: 'cut', keys: 'Ctrl+X' },
      { id: 'copy', keys: 'Ctrl+C' },
      { id: 'paste', keys: 'Ctrl+V' },
      { id: 'delete', keys: 'Del' },
    ],
  },
  {
    id: 'study',
    entries: [
      { id: 'close', keys: 'Esc' },
      { id: 'resize', keys: '← →' },
    ],
  },
]

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false
  }
  return (
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.tagName === 'SELECT' ||
    target.isContentEditable === true
  )
}
