import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, test } from 'vitest'

import { AI_TAB_SECTIONS, SETTINGS_TABS, TOOLS_TAB_SECTIONS } from './SettingsPage'

// Settings-structure conformance wall (ADR-0033 / plan 27): the settings
// nav in this app must match the family contract vendored at
// contracts/settings-map.json. Placement changes go through the dev
// canonical copy first — never by editing the vendored file (which
// scripts/verify-wiring.sh keeps byte-identical) or the arrays alone.
const map = JSON.parse(
  readFileSync(join(__dirname, '..', '..', '..', '..', 'contracts', 'settings-map.json'), 'utf8'),
) as {
  products: Record<
    string,
    { tabs: { id: string; group: string; sections?: { id: string; domains: string[]; status?: string }[] }[] }
  >
}

const declared = map.products['study-assistant'].tabs

const declaredSections = (tabId: string) =>
  (declared.find((tab) => tab.id === tabId)?.sections ?? []).map((section) => section.id)

describe('settings-map contract', () => {
  test("the vendored map declares study-assistant's tabs exactly as shipped", () => {
    expect(declared.map((tab) => tab.id)).toEqual([...SETTINGS_TABS])
  })

  test("the declared ai tab sections match the app's AI sections", () => {
    expect(declaredSections('ai')).toEqual([...AI_TAB_SECTIONS])
  })

  test("the declared tools tab sections match the app's tools sections", () => {
    expect(declaredSections('tools')).toEqual([...TOOLS_TAB_SECTIONS])
  })

  // INV-1/INV-2 (enforced part): every aligned section hosts only its own
  // group's domains. Pending sections are recorded debt with a target home
  // in the map — they must not gain new aligned settings on the way out.
  test('aligned ai sections host only ai.* domains (no tools drift back in)', () => {
    const ai = declared.find((tab) => tab.id === 'ai')
    expect(ai).toBeDefined()
    for (const section of ai!.sections ?? []) {
      if (section.status === 'pending') continue
      for (const domain of section.domains) {
        expect(domain.startsWith('ai.')).toBe(true)
      }
    }
  })

  test('tools sections host only tools.* domains', () => {
    const tools = declared.find((tab) => tab.id === 'tools')
    expect(tools).toBeDefined()
    for (const section of tools!.sections ?? []) {
      expect(section.status ?? 'aligned').toBe('aligned')
      for (const domain of section.domains) {
        expect(domain.startsWith('tools.')).toBe(true)
      }
    }
  })

  test('web search and discovery live in the tools tab declaration, not under ai', () => {
    const ai = declared.find((tab) => tab.id === 'ai')!
    const flatAiDomains = (ai.sections ?? []).flatMap((section) => section.domains)
    expect(flatAiDomains).not.toContain('tools.web-search')
    expect(flatAiDomains).not.toContain('tools.discovery')
    const tools = declared.find((tab) => tab.id === 'tools')!
    expect((tools.sections ?? []).flatMap((section) => section.domains)).toEqual(
      expect.arrayContaining(['tools.web-search', 'tools.discovery', 'tools.indexing']),
    )
  })
})
