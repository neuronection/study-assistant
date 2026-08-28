# Task activity and retries

Everything heavy — file ingestion, OCR, extraction post-processing, chat turns —
runs as background tasks. When a task fails (for example OCR cannot read a scan),
nothing is lost: the failure is recorded with its error, and you can retry it.

## The activity button

The rail's footer has an **activity button** (pulse icon). A red badge with a number
means failed tasks are waiting. Click it to open the activity panel:

- **Failed** — each row shows what was being processed, when it finished, and the
  error. Press the ⭯ **retry** button on a row to requeue that one task, or the 🗑
  **delete** button to remove that record outright (a confirmation asks first).
- Rows marked **source removed** point at a file or conversation that no longer
  exists — retrying them can never succeed, so retry is hidden and deleting them is
  the sensible cleanup.
- **Retry all N failed** — one press requeues every retryable failure in the list.
- **Delete all failed** (trash icon next to the section title) — removes every failed
  record at once after confirmation.
- **Delete source-missing (N)** — appears only when failures reference deleted
  files/conversations and clears exactly those hopeless rows.

The panel refreshes itself while it is open, so retried items move from *Failed* to
*In progress* on their own. Deleting the last failed failure clears the red badge too.

## The full task-activity page

The panel's **View all tasks** link opens a dedicated `/jobs` page for the complete
picture — useful when many items failed at once:

- Every recent task as a card with its **name**, **type chip** (`ingest`,
  `postprocess`, …), **status chip including the stage where it stopped**
  (for example `failed · ocr`), the job id and exact start/finish times.
- **Name links straight to the material** behind the task (when there is one), so
  you can open the file that failed to inspect or replace it.
- The error text is shown in full — click it to expand/collapse long tracebacks.
- Status tabs (**Failed / Running / Queued / Done / All**) with live counts, plus
  search by name or id; **Retry all failed** sits in the header.
- A **Type** filter narrows the list to one task kind, and a **Completed /
  Started / Created** switcher sorts by that date, oldest or newest first. Tabs,
  type, sorting and direction are part of the URL, so a filtered view can be
  bookmarked or reopened later exactly as it was.
- Failed and done rows carry a small **delete** button (confirmation first); the
  header **Delete…** menu offers *Delete all failed* — scoped to the active Type
  filter when one is set — and *Delete source-missing (N)* for the hopeless ones.
  Queued and running tasks cannot be deleted mid-flight.

The page refreshes every few seconds; retried rows flip to *Running* on their own,
and deleted rows simply disappear from every view.

## Deleting versus retrying

Retrying is the fix attempt; deleting is bookkeeping. Nothing in your content is
touched by either — a task record is just an entry in the activity log. Two rules of
thumb:

1. If the cause can be fixed (provider was down, file temporarily locked), retry.
2. If the record is noise forever (the material or chat was already deleted), delete
   it — individually, filtered by type, or via the source-missing shortcut.

Failed tasks are **never** removed automatically: they keep the red badge honest
until you decide. Completed records without any error are tidied up automatically
after roughly two weeks so the history stays lightweight.

## Retrying straight from the Library

In the Library, right-click (or open the ⋯ menu on) a file:

- **Re-ingest (OCR again)** — runs the full ingestion again: scanned pages are
  sent back through OCR, text PDFs and Markdown/text files are re-extracted. Works
  on a multi-selection too (**Re-ingest N files**); each eligible file gets its own
  task, and the item appears whether or not the file was selected beforehand — a
  right-click acts on exactly what you clicked.
- **Retry failed AI tasks for this file** — appears only when this exact file has
  failed background tasks; it requeues those tasks without touching anything else.

## What can be retried

Task types the app knows how to run again — file ingestion (`ingest`) and
extraction post-processing (`postprocess`, embeddings + index cards) — are
retryable; individual failures and bulk retries refuse anything else. Chat turns
are never retried this way (a turn belongs to its conversation). Retrying resets a
task to the queue with a fresh attempt — previously extracted data is replaced if
the attempt succeeds.

## Common case: an upload fails during OCR

1. The material's card shows a **failed** state pill; the activity button shows the
   red badge.
2. Open the panel, read the error (for example "OCR provider unavailable").
3. Fix the cause if there is one — check Settings → Models for provider issues —
   then press **retry** on the row or **Retry all**.
4. Watch the item move through *In progress* until it completes.

If a task keeps failing after several attempts, the error text in the panel is the
same detail recorded by the backend — copy it from the row tooltip when asking for
help.
