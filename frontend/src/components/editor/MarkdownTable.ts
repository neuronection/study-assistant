import { Table } from '@tiptap/extension-table'

interface CellContent {
  textContent: string
  childCount: number
}

interface CellLike {
  firstChild: CellContent | null
}

interface RowLike {
  childCount: number
  forEach: (cb: (cell: CellLike, _offset: number, index: number) => void) => void
}

interface TableSerializerState {
  write: (payload: string) => void
  ensureNewLine: () => void
  closeBlock: (node: unknown) => void
  renderInline: (node: CellContent) => void
  inTable: boolean
}

export const MarkdownTable = Table.extend({
  addStorage() {
    return {
      markdown: {
        serialize(
          state: TableSerializerState,
          node: { forEach: (cb: (row: RowLike, _offset: number, index: number) => void) => void }
        ) {
          state.inTable = true
          node.forEach((row, _rowOffset, rowIndex) => {
            state.write('| ')
            row.forEach((cell, _cellOffset, cellIndex) => {
              if (cellIndex) {
                state.write(' | ')
              }
              const cellContent = cell.firstChild
              if (
                cellContent !== null &&
                (cellContent.textContent.trim() !== '' || cellContent.childCount > 0)
              ) {
                state.renderInline(cellContent)
              }
            })
            state.write(' |')
            state.ensureNewLine()
            if (!rowIndex) {
              const delimiterRow = Array.from({ length: row.childCount })
                .map(() => '---')
                .join(' | ')
              state.write(`| ${delimiterRow} |`)
              state.ensureNewLine()
            }
          })
          state.closeBlock(node)
          state.inTable = false
        },
        parse: {},
      },
    }
  },
})
