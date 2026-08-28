export interface MindmapNode {
  id: string
  label: string
  startLine: number
  endLine: number
  depth: number
  children: MindmapNode[]
}

export interface ParsedMindmap {
  lines: string[]
  titleLine: number | null
  roots: MindmapNode[]
}

const LIST_RE = /^(\s*)([-*+])\s+(.*)$/
const HEADING_RE = /^(\s*)(#{1,6})\s+(.*)$/
const TITLE_RE = /^\s*#\s+/

export function stripInlineMarkdown(text: string): string {
  return text
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\*\*([^*]+?)\*\*/g, '$1')
    .replace(/__([^_]+?)__/g, '$1')
    .replace(/(?<!\*)\*([^*]+?)\*(?!\*)/g, '$1')
    .replace(/(?<!_)_([^_]+?)_(?!_)/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\$\$([^$]+?)\$\$|\$([^$]+?)\$/g, (_m, block, inline) => (block ?? inline).trim())
    .replace(/~~([^~]+?)~~/g, '$1')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .trim()
}

function parseLine(
  line: string,
): { depth: number; label: string; marker: string } | null {
  const li = line.match(LIST_RE)
  if (li) {
    return { depth: li[1].length, label: stripInlineMarkdown(li[3]), marker: `${li[2]} ` }
  }
  const heading = line.match(HEADING_RE)
  if (heading) {
    return {
      depth: heading[1].length,
      label: stripInlineMarkdown(heading[3]),
      marker: `${heading[2]} `,
    }
  }
  return null
}

export function parseMindmap(markdown: string): ParsedMindmap {
  const lines = markdown.split('\n')
  let titleLine: number | null = null
  for (let i = 0; i < lines.length; i += 1) {
    if (TITLE_RE.test(lines[i])) {
      titleLine = i
      break
    }
  }
  const roots: MindmapNode[] = []
  const stack: MindmapNode[] = []
  const start = titleLine !== null ? titleLine + 1 : 0
  for (let i = start; i < lines.length; i += 1) {
    const parsed = parseLine(lines[i])
    if (parsed === null) {
      continue
    }
    const node: MindmapNode = {
      id: String(i),
      label: parsed.label,
      startLine: i,
      endLine: i + 1,
      depth: parsed.depth,
      children: [],
    }
    while (stack.length > 0 && stack[stack.length - 1].depth >= node.depth) {
      const done = stack.pop()
      if (done) {
        done.endLine = i
      }
    }
    if (stack.length > 0) {
      stack[stack.length - 1].children.push(node)
    } else {
      roots.push(node)
    }
    stack.push(node)
  }
  while (stack.length > 0) {
    const done = stack.pop()
    if (done) {
      done.endLine = lines.length
    }
  }
  return { lines, titleLine, roots }
}

export function serialize(lines: string[]): string {
  return lines.join('\n')
}

export function editNodeLabel(
  lines: string[],
  node: MindmapNode,
  label: string,
): string[] {
  const next = lines.slice()
  const line = next[node.startLine]
  const prefix = line.match(/^(\s*(?:[-*+]|#{1,6})\s+)/)
  next[node.startLine] = (prefix ? prefix[1] : '') + label.trim()
  return next
}

export function removeNode(lines: string[], node: MindmapNode): string[] {
  const next = lines.slice()
  next.splice(node.startLine, node.endLine - node.startLine)
  return next
}

export function addChildNode(
  lines: string[],
  node: MindmapNode,
  label: string,
): string[] {
  const next = lines.slice()
  const parentLine = next[node.startLine]
  const indent = (parentLine.match(/^(\s*)/) ?? ['', ''])[1] + '  '
  const marker = parentLine.includes('#') ? '## ' : '- '
  next.splice(node.endLine, 0, `${indent}${marker}${label.trim()}`)
  return next
}

export function addRootNode(lines: string[], label: string): string[] {
  const next = lines.slice()
  let insertAt = next.length
  while (insertAt > 0 && next[insertAt - 1].trim() === '') {
    insertAt -= 1
  }
  next.splice(insertAt, 0, `- ${label.trim()}`)
  return next
}
