import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { IcsImportDialog } from './IcsImportDialog'

const previewIcsImport = vi.fn()
const importIcs = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    previewIcsImport: (courseId: string, file: File) => previewIcsImport(courseId, file),
    importIcs: (courseId: string, file: File, confirm: boolean) =>
      importIcs(courseId, file, confirm),
  }
})

const PREVIEW = {
  events: [
    { uid: 'lecture-1', title: 'Calculus lecture', date: '2026-10-26', time: '10:00', detail: 'Room 4', kind: 'study' },
    { uid: 'exam-1', title: 'Midterm exam', date: '2026-11-02', time: null, detail: '', kind: 'milestone' },
  ],
  exam_candidates: [{ uid: 'exam-1', title: 'Midterm exam', date: '2026-11-02' }],
  total_events: 2,
  skipped: 0,
}

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <IcsImportDialog open courseId="c1" onClose={() => undefined} />
    </QueryClientProvider>
  )
}

describe('IcsImportDialog', () => {
  test('stages a preview and commits with the exam confirmation', async () => {
    previewIcsImport.mockResolvedValue(PREVIEW)
    importIcs.mockResolvedValue({ created: 2, updated: 0, exam_date: '2026-11-02' })
    renderDialog()
    const file = new File(['BEGIN:VCALENDAR'], 'timetable.ics', { type: 'text/calendar' })
    fireEvent.change(screen.getByLabelText('Choose an .ics file'), {
      target: { files: [file] },
    })
    expect(await screen.findByText('Calculus lecture')).toBeInTheDocument()
    expect(screen.getByText('2 events · 0 skipped')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /^Import$/ }))
    await waitFor(() => expect(importIcs).toHaveBeenCalledWith('c1', file, true))
    expect(await screen.findByRole('status')).toHaveTextContent('2 created · 0 updated')
  })

  test('shows the parser error for a malformed file', async () => {
    previewIcsImport.mockRejectedValue(new Error('not an iCalendar file'))
    renderDialog()
    fireEvent.change(screen.getByLabelText('Choose an .ics file'), {
      target: { files: [new File(['hello'], 'bad.ics', { type: 'text/calendar' })] },
    })
    expect(await screen.findByRole('alert')).toHaveTextContent('not an iCalendar file')
    expect(screen.getByRole('button', { name: /^Import$/ })).toBeDisabled()
  })
})
