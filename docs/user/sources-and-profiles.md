# Linked folders and profiles

## Linked folders

Uploads are fine for one-off files. Linked folders are for material that lives on
your disk and keeps changing — lecture directories, a shared course folder.

**Library → Linked folders → link one**: give it a label and the folder's path.
Then **scan** whenever you want (or before each study session):

- New matching files (PDF, images, Markdown, text) become materials and are
  ingested like uploads.
- Files you edited are detected (cheap stat check first — unchanged files are
  skipped without reading) and re-ingested as a **new extraction version**, so
  the history of what changed is preserved.
- Files you delete are marked *missing* — nothing is destroyed; if the file
  returns, it is re-ingested.
- Content is always copied into the app's own store, so your library keeps
  working even if the source folder goes away.

## Profiles

The rail's bottom-left profile button opens a **Profiles overlay**. Each profile is a
completely separate study space — its own courses, library, notes, cards, and scores.

- Click any row in the overlay to switch; the current one is highlighted and the
  choice is remembered per device.
- **Add a profile** — the button at the bottom of the overlay opens the name
  form; name it (e.g. *Exam prep*, or a sibling's space), confirm, and you are
  switched to it immediately. Cancel returns to the list.
- The trash button deletes non-default profiles (hover a row); the **Default
  profile** cannot be deleted, and a profile that still owns content is refused by
  the backend — clear it first.

## Sample course

Starting from nothing? The Today screen offers **Create sample course**: a small
Calculus I course with three real lessons is added, searchable immediately — the
fastest way to try outlines, quizzes, and the tutor.
