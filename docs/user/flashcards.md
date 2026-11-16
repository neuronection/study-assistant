# Flashcards

Spaced-repetition review with FSRS scheduling, fed by your own material.

Card review lives in two places. The workspace **Practice tab → Flashcards
segment** (open a node → Practice, then flip the small
*Quizzes & exercises / Flashcards* switcher) queues that node and its children,
and the segment's own action bar covers generating cards plus **Anki
import/export**. The global **Review** page (sidebar → **Review**, with a
due-count badge) clears due cards across **all courses** in one keyboard
session: cards carry their course chip, `1–4` rate (space reveals), a progress
bar tracks the batch, and time spent logs into your study-time analytics.
Old `?tab=cards` links and `/flashcards` URLs still land in the course
workspace.

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

**Review ahead** (the *Ahead N days* filter) shows cards before they are due.
Preview ratings are logged for your time and streak but do **not** change the
schedule; tick **Reschedule as reviewed** if you want them to. The daily review
cap from Study pace hides the rest of the queue with an honest capped banner.
Named filters can be saved and reused; **Due today** is the default.

**Study pace** (Settings → General) controls how much the scheduler asks of
you: Light / Standard / Intense presets, a retention target, maximum interval,
daily new/review caps, leech handling, sibling burying and load balancing. The
defaults match the previous schedule; changing them only affects future
intervals. Per-course overrides are available from the course's scheduling
settings.

Ratings taken without a connection are queued on the device and replayed
with their original review time when you reconnect; a **rating saved offline**
pill shows the pending count and a **Sync now** action. The queue is the same
one used by the capture inbox, so one failed rating never blocks the rest.

The review queue shows what's due. For each card:

1. Read the front, work out the answer.
2. **Show answer**.
3. Rate yourself: **Again** (blanked), **Hard**, **Good**, or **Easy**.

FSRS (a modern spaced-repetition algorithm) schedules the next review from your
rating history — early reviews grow intervals quickly, lapses pull cards back.
The card list shows each card's state and due date. That's it: come back when
cards are due, the queue does the rest.
