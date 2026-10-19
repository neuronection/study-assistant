import type { IntegrationDocsNode } from '@/components/ui/integration-docs-dialog'

/** The extensionDocsTree form (plan 34 §10) as the client-side shape —
 * the wire type is generated as a loose record, so the docs views narrow
 * it here, once. */
export interface DocsTreeItem {
  id: string
  file?: string
  title?: string
  description?: string
  index?: boolean
  audience?: 'user' | 'dev'
}

export interface DocsTreeCategory {
  category: string
  title?: string
  items: DocsTreeItem[]
}

export interface DocsTree {
  version: number
  categories: DocsTreeCategory[]
  i18n?: {
    defaultLocale?: string
    locales?: Record<string, Record<string, string>>
  }
}

export function asDocsTree(tree: unknown): DocsTree | null {
  return (tree ?? null) as DocsTree | null
}

/** Study's per-extension docs tree (plan 34 §10) as the kit's generic node
 * tree; file nodes carry the file path as their id. Category/item labels
 * resolve through the tree's own i18n map when present (requested locale,
 * then defaultLocale), else the inline title override, else the
 * title-cased slug — the family string rule, minimal form (health's
 * integrationViews precedent). */
export function docsNodes(
  tree: DocsTree | null | undefined,
  locale?: string | null,
): IntegrationDocsNode[] {
  const i18n = tree?.i18n
  const label = (key: string, inline: string | undefined, slug: string): string => {
    const localeMap = (code?: string | null) =>
      code ? i18n?.locales?.[code]?.[key] : undefined
    return (
      localeMap(locale) ??
      localeMap(i18n?.defaultLocale) ??
      inline ??
      slug.replace(/(^|-)([a-z])/g, (_, sep: string, ch: string) =>
        sep ? ` ${ch.toUpperCase()}` : ch.toUpperCase(),
      )
    )
  }
  return (tree?.categories ?? []).map((category) => ({
    id: `category:${category.category}`,
    title: label(`category.${category.category}`, category.title, category.category),
    children: category.items.map((item) => ({
      id: item.file ?? item.id,
      title: label(`item.${item.id}`, item.title, item.id),
    })),
  }))
}

/** The landing rule (plan 34 §10.4): the item carrying `index: true`,
 * else the first item of the first category. Applied to the raw tree
 * (the kit node list carries no index flag). */
export function landingDocFile(
  tree: DocsTree | null | undefined,
): string | null {
  const items = (tree?.categories ?? []).flatMap((category) => category.items)
  const flagged = items.find((item) => item.index)
  return (flagged ?? items[0])?.file ?? null
}

/** The audience tag of the item owning `file` (plan 34 §10.6) — shown by
 * the dialog as a badge when present; never gates access. */
export function audienceOfFile(
  tree: DocsTree | null | undefined,
  file: string | null,
): 'user' | 'dev' | null {
  for (const category of tree?.categories ?? []) {
    for (const item of category.items) {
      if (item.file && item.file === file) {
        return item.audience === 'dev' ? 'dev' : item.audience === 'user' ? 'user' : null
      }
    }
  }
  return null
}
