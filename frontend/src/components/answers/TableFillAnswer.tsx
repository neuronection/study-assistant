import { useTranslation } from 'react-i18next'

import { MathInput } from '@/components/math/MathInput'
import { cn } from '@/lib/utils'

export interface TableCellSpec {
  kind: 'locked' | 'text' | 'numeric' | 'equation'
  text?: string
}

export interface TableFillInput {
  headers: string[]
  row_labels: string[]
  cells: TableCellSpec[][]
}

export function isTableFillInput(
  input: { widget: string } | null | undefined,
): input is TableFillInput & { widget: string } {
  return input?.widget === 'table_fill'
}

export function emptyTableGrid(input: TableFillInput): string[][] {
  return input.cells.map((row) => row.map(() => ''))
}

export function tableGridComplete(grid: string[][] | null, input: TableFillInput): boolean {
  if (grid === null) return false
  return input.cells.some((row, rowIndex) =>
    row.some(
      (cell, cellIndex) =>
        cell.kind !== 'locked' &&
        (grid[rowIndex]?.[cellIndex] ?? '').trim().length > 0,
    ),
  )
}

export function TableFillAnswer({
  input,
  value,
  onChange,
  disabled,
}: {
  input: TableFillInput
  value: string[][] | null
  onChange?: (next: string[][]) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const interactive = onChange !== undefined && disabled !== true
  const grid: string[][] =
    value ??
    input.cells.map((row) => row.map(() => ''))

  const update = (rowIndex: number, cellIndex: number, next: string) => {
    if (!interactive) return
    onChange?.(
      grid.map((row, r) =>
        row.map((cell, c) => (r === rowIndex && c === cellIndex ? next : cell)),
      ),
    )
  }

  return (
    <div className="border-border overflow-x-auto rounded-md border">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-subtle">
            <th className="border-border border-b px-3 py-2 text-left" aria-hidden />
            {input.headers.map((header, index) => (
              <th
                key={index}
                className="border-border border-b px-3 py-2 text-left font-medium"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {input.cells.map((row, rowIndex) => (
            <tr key={rowIndex}>
              <td className="border-border px-3 py-1.5 text-xs font-medium">
                {input.row_labels[rowIndex]}
              </td>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="border-border px-2 py-1.5 align-middle">
                  {cell.kind === 'locked' ? (
                    <span className="text-muted-foreground text-sm">{cell.text}</span>
                  ) : cell.kind === 'equation' ? (
                    <div
                      className={cn(
                        'border-border rounded-md border p-1',
                        !interactive && 'opacity-70',
                      )}
                    >
                      <MathInput
                        value={grid[rowIndex]?.[cellIndex] ?? ''}
                        onChange={(next) => update(rowIndex, cellIndex, next)}
                      />
                    </div>
                  ) : (
                    <input
                      className={cn(
                        'bg-surface border-border w-full min-w-20 rounded-md border px-2 py-1.5 text-sm',
                        !interactive && 'opacity-70',
                      )}
                      inputMode={cell.kind === 'numeric' ? 'decimal' : undefined}
                      aria-label={t('widgets.tablefill.cell', {
                        row: input.row_labels[rowIndex] ?? rowIndex + 1,
                        column: input.headers[cellIndex] ?? cellIndex + 1,
                      })}
                      disabled={!interactive}
                      value={grid[rowIndex]?.[cellIndex] ?? ''}
                      onChange={(event) => update(rowIndex, cellIndex, event.target.value)}
                    />
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
