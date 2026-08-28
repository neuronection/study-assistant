# Notes and handwriting

Notes live where you explore: the **Notes tab of a course workspace**. Every note
is markdown (LaTeX for math when you use it), plus handwritten drawings whose text
is extracted by OCR for you.

## Where notes live

- **Workspace Notes tab** (course root or any node): lists the notes of that node
  *and everything below it* — rows carry a scope chip showing which node a note
  belongs to. A single click selects a row (file-browser style, Ctrl/Shift to
  extend); **double-clicking** opens the note in a **drawer over the workspace**, so
  you keep your place; close it with the ×, a click on the backdrop, or the back
  button. The **⤢ / ⤡ button in the drawer header expands the editor to full
  width** (and back), handy while writing long notes; your choice is remembered.
- **New note here** creates a note at the current node and opens it in the drawer;
  **Draft notes** asks AI to draft study notes from the node's material.
- Every row has a **⋯ menu** (or right-click): **Rename** and **Delete** —
  deleting removes the note together with its drawings. The toggle next to the
  search button switches between list and grid cards (remembered per browser).
- **Drag notes to re-file them**: grab a note row (or, with several selected, grab
  any one of them) and drop it onto a **node in the structure sidebar** — every
  dragged note moves to that node. When you drag a whole selection the drag image
  shows an "N items" badge.
- **Ctrl+K** palette: type part of a note's title — `note: …` results jump
  straight to the note in a full-page editor. The palette's **New note** action
  also opens the full-page editor. Prefix your query with **`?`** (e.g.
  `?chain rule`) to search **inside all your material** — results deep-link to
  the matching document.

### The standalone note page

Opening a note as its own page (from a chat mention chip, a proposal card or a
refreshed deep link) shows the same editor with focus chrome: the **✕**
returns to where you came from (falling back to the note's workspace Notes
tab), and the action row has a **Delete** button — confirmed before the note
(and its drawings) is removed, then takes you back.
- The drawer shows a small breadcrumb (course ▸ … ▸ node) linking back to where
  the note lives.

## Study alongside your material (split view)

Reading and note-taking don't have to be two screens. Open a material from the
workspace Materials tab and press **Take notes** in its header: a full-height
**split view** opens over the workspace — the material (Extraction / Original /
Side-by-side tabs) on the left, a note on the right. A fresh note is created on
the material's node the first time; the URL carries the split, so back/forward
and deep links work.

- **Drag the divider** to resize; the split is remembered per course
  (30–70 %).
- **Quote into note:** select any passage in the material and press the floating
  **Quote into note** button — a blockquote of the selection (with a link to
  the material) lands in your note at the cursor.
- From an open note, **Study alongside** offers the reverse: pick a material
  and the same split opens with your existing note on the right.
- Closing the pane (✕ / Escape) keeps everything you typed — the note editor
  autosaves.

On narrow screens the split falls back to the regular material drawer.

## Writing a note

The editor is a rich-text editor with a formatting toolbar (bold/italic, headings,
lists, quotes, code, undo/redo) — everything is stored as markdown behind the
scenes. The toolbar stays visible: long note bodies scroll **inside** the editor
while the toolbar stays pinned above. Undo/redo (also Ctrl+Z / Ctrl+Shift+Z)
steps back and forward through your edits — across saves too. Math is
typed directly: `$...$` inline, `$$...$$` display — it **renders live** in the
editor, and double-clicking a formula opens the MathLive equation editor
(with a Close button). Mermaid diagrams (` ```mermaid ` fences) render as
real diagrams too; double-click one to edit its source in a separate editor.
The toolbar's **Σ button** inserts a fresh equation and opens the equation
editor right away; the **diagram button** drops in a small starter flowchart
with its source editor open — no syntax memorized required.

**Notes save themselves.** As you type, the editor autosaves (a small status
indicator next to **Save** shows *Unsaved / Saving… / Saved*); **Save** flushes
immediately. Saving is non-disruptive: your line spacing and blank lines between
text are preserved exactly, the cursor position stays where it is — autosave
never rewrites what you see, and in-editor undo/redo keeps working across saves.
Empty lines above the first line or below the last line of text are dropped on
save (they carry no content). Closing the editor or the
app with unsaved text is safe: a local draft copy is kept, and the next time
you open the note you'll be offered to **Restore** it. If the same note was
edited in another window in the meantime, you'll be asked whether to
**reload theirs** or **keep mine** — nothing is overwritten silently. Notes
always belong to a course; notes created from a workspace belong to that course
and node.

## Version history

The **History** button in the editor's action row lists snapshots of earlier
states of the note. Snapshots are taken automatically as the note changes
(coalesced: at most one every 10 minutes, so typing sessions don't flood the
list) and marked by cause — *autosave*, *manual*, *restore*. Pick a version to
preview it rendered exactly like the note, then:

- **Restore** makes that content the note's body again — as a new snapshot, so
  a restore itself can be undone.
- **Save version now** checkpoints the current state immediately (bypasses the
  coalescing window).

Up to 50 versions are kept per note (oldest pruned). If you have unsaved edits
when restoring, you'll be warned — restoring discards them.

## Tags

Tags keep large note collections organized:

- In the editor, use the **Add tag** link under the title — tags are lowercase
  and short; remove one with the × on its chip.
- The workspace Notes tab has a **filter-chip bar** (All / the course's tags) —
  pick a tag to filter the list; **New note here** inherits the active filter's
  tag.
- Search matches titles, body text and OCR'd handwriting; the list grows with a
  **Load more** button as you scroll back in time.

## Handwriting

Open a note and press the **pen button in the editor toolbar** — a large
handwriting canvas opens over the editor, and the drawing lands **right where
your cursor was**:

1. Write on the canvas. The toolbar has a **pen and an eraser**
   (stroke-erase), four ink colors, three pen widths, undo/redo and a guarded
   clear. Stylus pressure varies the stroke width. The canvas is **infinite**:
   scroll to zoom (the view zooms toward the cursor), drag with the **middle
   mouse button** — or hold **Space** and drag, or pick the **hand tool** — to
   pan in any direction. A small **floating bar** in the bottom-left corner has
   zoom out / the current zoom % / zoom in, **Fit drawing** and **1:1** (actual
   size); the percent doubles as a reset-to-100% button. The **⛶ button** on
   the toolbar toggles the canvas to **fullscreen** for large sketches
   (Escape leaves fullscreen first).
2. Press **Save drawing**. The drawing is inserted into the note as an
   **inline image** at the cursor, right between your text — the saved PNG is
   **cropped to your strokes** (plus a small margin), so empty canvas space is
   never stored. **Run OCR**
   (on by default) extracts the handwritten text — any math in it comes back
   as LaTeX in a collapsible *OCR text* line under the image. Turn it off to
   save just the drawing with no text extraction.
3. Click a drawing to focus it: it gets a highlight ring and its small **⋯
   menu** appears. **Edit drawing** reopens
   the canvas with your strokes loaded **at the same 100% scale as the saved
   image** (saving replaces the image — and reruns
   OCR if the toggle is on; with it off, any old OCR text is cleared since it
   no longer matches), **Run OCR again** re-extracts the text (each attempt is
   versioned), **Copy OCR text** puts the extracted text on the clipboard, and
   **Delete drawing** (confirmed) removes the drawing — and its OCR text —
   from the note, dropping the image where it stood. Clicking elsewhere in the
   note (or arrowing away) unfocuses the drawing and hides the menu. To move a
   drawing, **drag its image** (the cursor shows a grab hand) and drop it
   anywhere else in the note — even between other paragraphs.

Drawings are part of the note's body: they keep their position between text
and survive saves/version history; the AI sees their OCR text *at the position
they appear* when you generate quizzes or ask the tutor about the note. A
drawing that is **not referenced** in the body (e.g. created before inline
insertion existed) appears as a card below the editor with an **Insert inline**
action and the same **⋯ menu** (including **Delete drawing**) — once referenced
it lives only in the body. Your strokes are kept
forever as the source of truth: the image never degrades, and OCR can improve
as models change. The PNG render is stored content-addressed like all
originals.

## AI note actions

The **AI** button above the editor opens a menu: **Summarize**, **Clean up**,
**Explain**, **Expand** run the note (plus its drawings' OCR text) through an
AI transform under strict output rules. The result appears in a panel as an
**editable draft** — tweak it first (fix notation, drop a paragraph), then
**Append to note** adds it below your text; **✕** closes the panel without
appending. Every action is logged like all AI calls.

## Inline AI helper

The ✨ button (in the editor toolbar) opens the **AI helper**: select any text, then pick a transform
(**Explain**, **Answer the question**, **Make more compact**, **Expand with
details**, **Rewrite clearly**, **Simplify**, **Fix grammar**, **Improve
structure**, **Bullet points**, **Format as Markdown**, **Translate**), or type a
free-form instruction in the prompt box and press Enter. The **Context** chip
(orange when on) sends the selected text plus the surrounding note as context;
the **Course material** chip additionally grounds the result in your course's
notes and materials (it appears only when the note belongs to a course).

The result **streams into a preview** — press **Stop** to cut it short, or wait.
Then review and edit it in the preview, and choose **Replace selection** (keeps
your selected text's position), **Insert below** (a new block under the current
one), or **Insert at cursor**. **Regenerate** re-runs the same request;
**Discard** throws it away. Insertions respect your note's math, diagrams,
tables and drawings, and are undoable with Ctrl+Z. Without a selection, the
presets need text — the helper offers an explicit **Apply to whole note**
instead, and the prompt box writes new content at the cursor.

The AI helper is a small **floating window**: grab the grip bar at the top to
**move it**, and drag any edge or corner to **resize** it. It always stays
inside the window, so the action buttons are never pushed off-screen — if the
text is longer than the panel, only the text scrolls while the header and the
action buttons stay put.

## Dictation

The 🎤 button at the right end of the editor toolbar turns your voice into
text: click it, speak, and click **Insert** when you're done — the transcript
lands at your cursor like typed text (undoable with Ctrl+Z). While recording,
a small strip shows a timer and a live level meter; **Cancel** (✕) throws the
recording away without transcribing. The first time, your browser asks for
microphone permission.

Transcription runs through the **speech-to-text model** assigned to the
*Transcribe* task (Settings → AI → Tasks) — any Whisper-class model works,
including local whisper servers (see [getting-started.md](getting-started.md)
for provider setup). Without an assigned model, the strip tells you what to
configure. Dictation is available everywhere the rich editor appears: notes,
the extraction QA editor and the new text/markdown file dialog.

Rare editor actions live in the **⋯ overflow menu**: print, export `.md`,
version history and delete. **Make flashcards** and **Save** stay as direct
buttons.

## Flashcards from notes

**Make flashcards** (top of the editor) turns the note — text and OCR'd
handwriting — into a deck and drops the cards straight into your review queue.

## Searching notes

The **search button** (magnifier icon, next to the view toggle) expands into a
search box that filters the notes tab **as you type** (Enter applies
immediately, no waiting for the debounce). It matches titles, note text, **and
OCR'd handwriting** — searching `2x` finds the whiteboard photo where you
derived it. **Esc** (or clearing the box and clicking away) collapses it back
to the icon. The Ctrl+K palette searches note titles from anywhere.

## Flashcards from notes

See [flashcards.md](flashcards.md) — any note (including its drawings) can
become a deck.
