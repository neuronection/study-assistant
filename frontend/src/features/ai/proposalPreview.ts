import type { ChatProposal } from '@/lib/api'

export interface ProposalPreviewContent {
  title: string
  markdown: string
}

export function appendPreview(
  original: string,
  heading: string | undefined,
  markdown: string,
): string {
  const addition = heading ? `## ${heading}\n\n${markdown}` : markdown
  return original.trim()
    ? `${original.trimEnd()}\n\n${addition.trim()}`
    : addition
}

function payloadOf(proposal: ChatProposal): Record<string, unknown> {
  return (proposal.payload ?? {}) as Record<string, unknown>
}

function stringField(payload: Record<string, unknown>, key: string): string {
  const value = payload[key]
  return typeof value === 'string' ? value : ''
}

/** The rendered-content view for a proposal (plan 78-F): the markdown a
 * create would write, the resolved result of an anchored edit, or the
 * merged result of an append. Null for actions with nothing to render
 * (generations run in their dialog; placements carry no content). */
export function proposalPreview(
  proposal: ChatProposal,
): ProposalPreviewContent | null {
  const payload = payloadOf(proposal)
  const title = stringField(payload, 'title')
  switch (proposal.action) {
    case 'create_note':
    case 'create_material': {
      const body = stringField(payload, 'body_md')
      if (!body) return null
      return { title, markdown: body }
    }
    case 'edit_note': {
      const body = stringField(payload, 'new_body_md')
      if (!body) return null
      return { title, markdown: body }
    }
    case 'edit_material': {
      const body = stringField(payload, 'new_markdown')
      if (!body) return null
      return { title, markdown: body }
    }
    case 'append_note':
    case 'append_material': {
      const markdown = stringField(payload, 'markdown')
      if (!markdown) return null
      const heading =
        typeof payload.heading === 'string' ? payload.heading : undefined
      const original = stringField(payload, 'original_md')
      return { title, markdown: appendPreview(original, heading, markdown) }
    }
    default:
      return null
  }
}
