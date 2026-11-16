# Exam papers

Practice → **Exam papers** turns your question bank into a timed mock paper with
sections, marks and a grade scale. It is deliberately not a second quiz runner:
a paper is an activity snapshot, so the existing timer, autosave, submission and
print paths all apply.

## Assemble a paper

**New paper** opens the builder:

- **Title**, **duration** and optional **instructions**.
- One or more **sections**. Each section has a title, a question count and a
  marks total, and can restrict the draw to a difficulty band.
- A live **total marks** readout. Every question must receive at least one mark,
  so a section cannot have more questions than marks.

Questions are selected deterministically from the course bank for the same
blueprint (title, duration and sections). The same blueprint produces the same
paper; a custom seed changes the draw. Questions are copied into the paper at
assembly time, so later bank edits, regenerations or deletions do not change a
paper you already sat. Duplicate stems are skipped.

If a section asks for more questions than the bank can supply, assembly refuses
with the available count and leaves nothing behind.

## Sit it

**Sit** opens the focused runner in exam mode:

- the server sets a deadline from the paper duration and auto-submits at zero;
- hints and “ask about this question” are refused server-side;
- each submitted answer is acknowledged as **Answer saved** — correctness and
  explanations stay hidden until you submit the paper;
- the existing runner keeps your answers server-side, so a refresh or a short
  disconnect resumes the attempt.

## Marked report

After submitting, open **Report** on the paper row:

- marks earned out of the paper total, per section;
- the grade band, if the paper has one;
- answered versus total questions;
- **Marks lost by topic**, grouped by the concepts on each question, so you can
  see which topic cost the paper.

Reports use the partial credit already produced by deterministic and rubric
grading. A paper with no finished attempt shows an honest empty report.

## Print and export

**Print paper** and **Print answer key** reuse the existing quiz print surface:
sections, marks, question text and worked answers render through the same print
stylesheet, including KaTeX math.

## Limits in this first cut

- Bank-assembled papers only. Uploaded past-paper PDFs with a self-mark sheet
  are still planned.
- No predicted-grade calibration or forecast integration yet.
- Deleting a paper removes its activity and attempts after confirmation.
