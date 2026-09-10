import { Copy } from 'lucide-react'
import type { TFunction } from 'i18next'

import type { PopoverMenuItem } from '@/components/ui/popover-menu'
import { copyText } from '@/lib/clipboard'
import type {
  Block,
  CodeBlock,
  MathBlock,
} from './types'

export function mathMarkdown(block: MathBlock): string {
  return block.display ? `$$${block.latex}$$` : `$${block.latex}$`
}

export function fencedCode(block: CodeBlock): string {
  const lang = block.lang?.trim() ?? ''
  return `\`\`\`${lang}\n${block.code}\n\`\`\``
}

export function tableToMarkdown(rows: string[][]): string {
  if (rows.length === 0) {
    return ''
  }
  const cell = (value: string) => value.replace(/\n/g, ' ').replace(/\|/g, '\\|')
  const width = rows[0].length
  const line = (row: string[]) => `| ${row.map(cell).join(' | ')} |`
  const separator = `| ${Array.from({ length: width }, () => '---').join(' | ')} |`
  return [line(rows[0]), separator, ...rows.slice(1).map(line)].join('\n')
}

function item(key: string, label: string, payload: string): PopoverMenuItem {
  return {
    key,
    label,
    icon: Copy,
    onSelect: () => {
      void copyText(payload)
    },
  }
}

export type CopyableBlock = Extract<
  Block,
  { type: 'math' | 'code' | 'text' | 'diagram' | 'chart' | 'table' | 'geo' }
>

function isCopyableBlock(block: Block): block is CopyableBlock {
  switch (block.type) {
    case 'math':
    case 'code':
    case 'text':
    case 'diagram':
    case 'chart':
    case 'table':
    case 'geo':
      return true
    default:
      return false
  }
}

export function blockActionItems(block: Block, t: TFunction): PopoverMenuItem[] | null {
  if (!isCopyableBlock(block)) {
    return null
  }
  switch (block.type) {
    case 'math':
      return [
        item('copy-latex', t('blocks.copyLatex'), block.latex),
        item('copy-md', t('blocks.copyAsMarkdown'), mathMarkdown(block)),
      ]
    case 'code':
      return [item('copy-fenced', t('blocks.copyFenced'), fencedCode(block))]
    case 'text':
      return [item('copy-md', t('blocks.copyMd'), block.md)]
    case 'diagram':
      return [item('copy-mermaid', t('blocks.copyMermaid'), block.mermaid)]
    case 'chart':
      return [
        item('copy-json', t('blocks.copyFigureJson'), JSON.stringify(block.plotly, null, 2)),
      ]
    case 'table': {
      const md = tableToMarkdown(block.rows)
      if (!md) {
        return null
      }
      return [item('copy-table', t('blocks.copyTableMd'), md)]
    }
    case 'geo': {
      if (!block.jsxgraph.trim()) {
        return null
      }
      return [item('copy-geo', t('blocks.copyGeo'), block.jsxgraph)]
    }
    default:
      return null
  }
}
