import type { ActivationEvent, ActivationProps } from '@/lib/activation-vocab'
import { recordActivation } from '@/lib/api'
import { getLastSessionScope, scopeStorageKey } from '@/lib/session-scope'

const PREFIX = 'sa-first-event.'
const LOCAL_PREFIX = `${PREFIX}local.`
const pending = new Set<string>()

function removeKeysWithPrefix(prefix: string): void {
  try {
    const keys: string[] = []
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index)
      if (key !== null && key.startsWith(prefix)) {
        keys.push(key)
      }
    }
    for (const key of keys) {
      window.localStorage.removeItem(key)
    }
  } catch {
    void 0
  }
}

export function firstEventKey(scope: string | null, event: ActivationEvent): string {
  return `${PREFIX}${scopeStorageKey(scope)}.${event}`
}

export function recordFirstActivation(
  event: ActivationEvent,
  props?: ActivationProps | null
): void {
  const key = firstEventKey(getLastSessionScope(), event)
  try {
    if (window.localStorage.getItem(key) === '1' || pending.has(key)) {
      return
    }
  } catch {
    return
  }
  pending.add(key)
  void recordActivation(event, props)
    .then(() => {
      try {
        window.localStorage.setItem(key, '1')
      } catch {
        void 0
      }
    })
    .catch(() => undefined)
    .finally(() => pending.delete(key))
}

export function clearFirstEventKeys(scope: string | null): void {
  removeKeysWithPrefix(`${PREFIX}${scopeStorageKey(scope)}.`)
  removeKeysWithPrefix(LOCAL_PREFIX)
}

/** The pre-scope `local` bucket is shared by anonymous/desktop boot; it is
 * cleared with every session-loss path so a later user does not inherit
 * another user's first-event suppression. */
export function clearPreScopeFirstEventKeys(): void {
  removeKeysWithPrefix(LOCAL_PREFIX)
}
