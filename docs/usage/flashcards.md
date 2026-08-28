# Flashcards

Spaced-repetition review with FSRS scheduling, fed by your own material.

Card review lives in the workspace **Practice tab → Flashcards segment**
(open a node → Practice, then flip the small *Quizzes & exercises / Flashcards*
switcher): the review queue is scoped to that node and its children, and the
segment's own action bar covers generating cards plus **Anki import/export**.
Old `?tab=cards` links and `/flashcards` URLs still land here; there is no global
flashcards page — everything is course-scoped.

## Generating cards

**Generate** (in the Flashcards segment, or *Make flashcards* on a note)
opens the generate dialog; pick a source:

- **My mistakes** — cards built from your mistake notebook (each recent wrong
  answer becomes a card targeting that error).
- **A note** — cards from a note's text, including OCR'd handwriting.
- **A material** — cards from a material's extraction.

The dialog also takes a one-time instruction field and shows a live **context
preview**. Cards placed from a workspace Practice tab land on that node.

Generated cards are validated before entering the deck: fronts and backs must be
non-empty, cloze cards must have a real deletion, and duplicates of cards you
already have are rejected. The generator retries its own mistakes before you
ever see them.

You can also add a card manually — the same rules apply.

## Anki import and export

Both live in the workspace **Flashcards segment** of the Practice tab and act on
that course:

- **Import .apkg** — bring an existing Anki deck in: every note becomes a card
  (cloze cards with `{{c1::…}}` are detected automatically), the deck name is
  kept as the card's source.
- **Export Anki deck** — downloads an `.apkg` of the course's cards that opens
  directly in Anki.

## Reviewing

The review queue shows what's due. For each card:

1. Read the front, work out the answer.
2. **Show answer**.
3. Rate yourself: **Again** (blanked), **Hard**, **Good**, or **Easy**.

FSRS (a modern spaced-repetition algorithm) schedules the next review from your
rating history — early reviews grow intervals quickly, lapses pull cards back.
The card list shows each card's state and due date. That's it: come back when
cards are due, the queue does the rest.
