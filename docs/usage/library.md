# Library: materials, folders, search

The Library works like a file manager (Nemo-style): a breadcrumb bar, a main pane
with grid/list views, and one-click navigation. Every material belongs to **one
course** — with **All courses** selected (the root), the pane shows your courses as
cards; entering one scopes everything to it.

## Navigating

- Breadcrumbs (`All courses ▸ Calculus ▸ Lectures`) — click any segment to jump back.
- The **Up** button (or a breadcrumb segment) goes to the parent folder.
- **Double-click** a folder to open it, a material to open its detail page
  (course cards at the root still open on a single click). **Enter** opens the
  one selected item.
- **Grid ⇄ list** toggle (top right); your choice is remembered.
- Right-click a folder for Open / Cut / Paste into folder / Rename / Delete. Deleting
  a folder **removes it and everything underneath** — all subfolders and all files in
  the subtree are permanently deleted, and every node link (folder assignments and the
  deleted files' direct links) is removed too. The confirm dialog always tells you what
  will go: the subfolder/file counts and, compactly, every linked place
  (`Course / Node — 1 folder · 2 files`). Linked-source folders keep their **Unlink**
  action (keeps the files, moves them to course root); *Delete* on them removes the
  linked files as well.
- The status bar shows folder/material counts; entering a course from the root also
  selects it as the workspace course in the nav rail.

## Selecting, moving, copying (file-browser style)

- A **single click selects** an item — it never opens it (no more accidental
  drawers while building a selection). **Double-click** opens, **Enter** opens
  the single selection, **Ctrl+click** adds/removes items,
  **Shift+click** selects a range, and **drag on empty pane space** draws a
  selection rectangle. `Esc` or clicking the "N items selected" footer text clears
  the selection.
- **Right-click → Cut / Copy**, then right-click a folder (or the pane background)
  → **Paste** — or just **drag** items onto a folder or into the open folder.
  Cutting dims the items until you paste. Keyboard: `Ctrl+X` / `Ctrl+C` / `Ctrl+V`,
  `Delete`.
- **Copy creates a duplicate material** ("title (copy)") — same file bytes (stored
  once), a fresh copy of its latest extraction, immediately searchable; reading
  progress and node assignments are not copied. Folders can be cut/moved but not
  copied yet; linked folders are browse-only.
- **Assign to node…** (right-click a material selection) links every selected
  material to a course node in one go — pick the node from the course tree.
- **Assign folder to node…** (right-click a folder — linked-source folders
  included) places the whole folder at a course node: everything in it becomes
  part of that node's materials, and files added to the folder later join
  automatically. Deleting an assigned folder from the library works directly: the
  **Delete** dialog lists every linked place (and the subfolder/file counts), and
  *Delete folder and contents* removes the links and the whole subtree in one step.
  To keep files instead, unassign first (the workspace Materials tab lists assigned
  folders with an ✕).

## Uploading

- Everything create-related lives behind the toolbar **+ (New…)** button:
  *New folder*, *New text file*, *New Markdown file*, **Upload files…**,
  **Upload folder…**, and *Add linked folder…*. **Dragging** files or a folder
  anywhere over the app window also works — a full-window **"Drop to upload"**
  overlay appears showing where the upload will land, and dropping starts the
  upload right away: a folder's directory tree is recreated automatically and
  loose files go into the current location.
- Uploads go into the **currently open folder** (course root if none).
- **New text file** / **New Markdown file** opens the rich editor (live math,
  tables, diagrams, the pen). The editor is organized in two tabs — **Content**
  (the document itself) and **Description** (a short "what is this file about?"
  summary). Press **Create** to save the file — the dialog stays open so you can
  keep writing, and **Save** saves again without closing (content and
  description together; new drawings are committed along the way). **Done**
  closes it. Until the first Create nothing is created, so cancelling just
  discards your work.
- **Folder uploads keep their structure** — the directory tree is recreated as
  real library folders, reusing folders that already exist; junk files like
  `.DS_Store` are skipped.
- In the **desktop app** (Linux .deb/AppImage), *Upload folder…* opens the
  system's **folder picker** instead of the browser dialog (the embedded
  WebKitGTK view cannot pick directories). Everything else behaves the same:
  the tree is recreated and files upload with the same rules. In a browser,
  the regular directory picker is used.
- In the **desktop app**, dragging files or folders **from your file manager**
  onto the app window also opens the same "Drop to upload" overlay (the
  desktop delivers drops as file paths rather than browser file objects, and
  both are supported).
- Supported: text PDFs, scanned PDFs, images (PNG/JPG/WebP), Markdown, plain text,
  **Office/web documents** (`.docx`, `.pptx`, `.epub`, `.html`/`.htm`) and
  **lecture recordings** (audio: `.mp3`, `.m4a`, `.wav`, `.ogg`, `.opus`, `.mpga`;
  video: `.webm`, `.mp4`, `.mpeg`).
- Text PDFs are extracted locally (fast, free). Scanned PDFs and images go to the
  model assigned to the **OCR** task and come back as markdown with LaTeX math,
  tables and diagrams.
- **Office/web documents are converted** into markdown extractions: Word
  documents keep headings, tables, links and inline images; PowerPoint decks
  become `## Slide N — <title>` sections with speaker notes preserved as
  quotes; EPUB books follow their chapter order; HTML pages keep headings,
  tables and links. One honest limitation: **math written as equations**
  (MathML/OMML) cannot be converted faithfully by any offline tool — those
  spots appear as a `[math-block]` marker in the extraction for you to fix in
  the editor; embedded images (equation screenshots included) are extracted,
  shown in place, and sent to the **OCR** task so their text is searchable.
- **Recordings become transcripts**: audio/video uploads are sent to the model
  assigned to the **Transcribe** task and land as normal materials whose
  extraction is the transcript (searchable, quotable, quiz-generatable), with
  the source filename, duration and model noted at the top. Large recordings
  are warned about **at upload** (most providers cap transcription around
  25 MB) — use a local whisper server or split the file. Re-ingest
  re-transcribes into a new version (handy after switching to a better model).
- **Anything else is refused at the door** — uploading an unsupported type
  (`.doc`, `.rtf`, `.pages`, …) shows an instant "unsupported file type"
  message instead of creating a broken file. Legacy binary formats are not
  supported on purpose.
- Re-uploading the same file **to the same course** is detected (content hash) —
  nothing is processed twice. The same file in a second course is a separate
  material (bytes stored once on disk).

## The material page

Clicking a material opens a dedicated page. The **top action row** keeps the
frequent verbs together: **Ask AI**, **Take notes**, **Export .md** and a
**reading status dropdown** (the current state with a colored dot — Unread,
Reading or Studied — opens a small menu to switch; it's the same signal shown
on course cards). Anything less frequent lives in the ⋯ **More actions** menu
of the reading toolbar, so the page stays clean.

The reading toolbar above the content shows the extraction's version line on
the left and three compact controls on the right:

- **▶ Read aloud** — speak the document (click again for stop/speed; see
  [Printing & read-aloud](printing.md)).
- **✏️ Edit** — fix OCR mistakes in the rich-text editor (headings
  and lists are preserved exactly, **math renders live** — `$…$` inline and
  `$$…$$` display appear as typeset formulas, and Mermaid fences render as
  diagrams; **double-click either to edit it** — formulas in the MathLive
  equation editor, diagrams in a source editor); saving creates a new version,
  re-indexes search and re-embeds automatically.
- **⋯ More actions** — the less-frequent verbs:
  - **Print** — a clean print preview of the rendered document
    ([Printing](printing.md)).
  - **Save as material** — creates a standalone Markdown file from the
    (edited) extraction — useful once the QA is done and you no longer need
    the original scan: the new material is a normal `.md` file with its own
    copy of the content, named after the original (`report.pdf` saves as
    `report.md`; if that name is taken by different content, a counter is
    appended: `report_01.md`, `report_02.md`, …). It also appears everywhere
    the original was assigned: the original's chapter/section assignments are
    copied, and if you save from inside a node's workspace the new material is
    assigned to that node as well. Deriving twice without changes doesn't
    create duplicates (you'll see "an identical material already exists"
    instead); the original material is never modified or deleted. If the
    source had drawings, they come along (copied, with their references
    re-pointed) so the saved material is self-contained.
  - **History** — browse every saved version of the extraction: pick one to
    preview it, **Compare** any two versions (or the current one) as a
    color-coded unified diff — green lines added, red lines removed, with an
    `+added / −removed` counter — and **Restore this version** to make an
    older version current again. Restoring never deletes anything: it saves
    the old content as a *new* version, so a restore itself can be undone.

**Copying from the rendered view** — hover any formula, table, diagram, chart
or code block (in the reading view, chat messages, flashcard review or quiz
explanations) and a ⋯ **Copy options** button appears in its top-right corner:
formulas offer **Copy LaTeX** and **Copy as Markdown** (`$$…$$`), tables copy
as a markdown table, diagrams copy their mermaid source, charts their figure
JSON, and code blocks offer a fenced ``` block next to the direct **Copy code**
button. Keyboard users reach it with Tab.

Text and Markdown files get their own vocabulary, because for them the
"extraction" *is* the document:

- **Formatted** — the rendered document (math, tables, drawings), exactly the
  Extraction view above (History, Save as material in the ⋯ menu; Edit in the
  toolbar).
- **Raw text** — the markdown source in monospace, for copy-paste or
  fine-grained inspection.
- **Description** — a short summary of the file. Write it from the editor's
  **Description** tab (press **Edit**, then switch from **Content** to
  **Description** — Saving persists both in one go).

You don't need to open a file to save its extracted text: in the Library and
in a node's **Materials** tab, right-click one or more selected files and
choose **Save as material** (multi-selections show **Save N as materials**).
Files without extracted text yet (still processing or failed) are skipped and
reported, never blocking the rest.
- **Original** — the untouched uploaded file (PDF/image viewer).
- **Side-by-side** — original ⇄ extraction for OCR QA.

### Drawing in a text/Markdown material

Text and Markdown materials have the same handwriting tools as notes: press the
**pen button** in the editor toolbar (while editing the extraction), draw, and
**Save drawing** — it lands inline at the cursor. Drawings keep their strokes in
the app, so you can reopen, re-edit and re-run OCR on them (the **⋯ menu** on a
drawing: Edit / Run OCR again / Copy OCR text / Delete); their text is searched
and seen by the AI just like typed content. The **new text/Markdown file dialog
has the pen too** — drawings you add there are held in the dialog and committed
with the file when you press Create (nothing is created before that, so cancel
just discards them; OCR for them runs at Create; drawings added after the first
save are committed by the next **Save**).

**Export .md** (header of the material page) downloads the extraction as a
self-contained Markdown file: drawings are embedded as images, so the file opens
anywhere — while the copy in the app keeps your strokes editable.

### Ask the AI while reading

The top action row has an **Ask AI** button. It opens a small popover showing
the material you're in, a row of suggested questions (**Explain simply**,
**Summarize**, **Key terms**, **Worked example**, **Quiz me**) and a text box.
Chips only fill the text box — nothing is sent until you press **Ask**, so you
can reword any suggestion first (**Quiz me** additionally switches that chat
into quiz-me mode). The question opens the tutor sidepanel with this material
attached (the tutor can READ it and cite it), and every ask about the same
document lands in **one conversation** — ask again later and the history stays
together.

Even faster for specific passages: **select any text** in the reading view and
a small toolbar appears — **Ask AI about this** opens the sidepanel with your
selection quoted above the cursor, ready for your actual question (in the
split study view the same toolbar also offers quote-into-note).

The sidepanel and the material drawer don't fight for the screen: the drawer
slides left to make room while you chat, and expands back when you close the
chat.

### AI helper while editing

While editing an extraction (or a new text/Markdown file), the **✨ button** in
the editor toolbar opens the same AI helper as notes: select text and pick a
transform (explain, answer, compact, expand, rewrite, simplify, grammar,
structure, bullets, format-as-markdown, translate), or type a free-form prompt.
The **Course material** chip grounds the result in this course's notes and
materials. Streamed results insert as **Replace selection**, **Insert below** or
**Insert at cursor** and are undoable. Selections can include **diagrams,
formulas and tables** — not just text — and a **Try to fix** entry appears when
the selection contains a broken math/diagram block. See
[notes.md](notes.md#inline-ai-helper) and
[notes.md#select-anything-ask-the-ai](notes.md#select-anything-ask-the-ai)
for details.

The header shows status, the owning course, chips for where the material is
assigned (course/chapter/section), a reading-status control
(unread / reading / studied) used by progress features, and — when the course is
known — a **Take notes** button that opens the split study view (material left,
your note right) in the course workspace. See the notes guide for the split view
and the quote-into-note bridge.

## Sharing whole courses

The Courses page can **export a course** as a single `.zip` bundle (content only
— materials, notes, quizzes, exercises, the outline; none of your personal
history) and **import** one from a classmate: a preview shows what's inside
before anything is added, and the course lands as a new workspace.

The back arrow (and the Library breadcrumb) returns to **where you opened the
material from** — the folder you were browsing, or the page that linked here.
Materials opened from a course workspace never take this path: they open as a
drawer over the workspace instead (see the courses guide).

> **Migrating from the old global library?** Materials that had no course were moved
> into an auto-created **Unsorted** course. Re-assign them by re-uploading to the
> right course (or keep them there) — the Unsorted course can be deleted once empty.

### Mindmaps

When a material's extraction is a mindmap (e.g. composed by the AI), the
Extraction view renders it as an interactive map you can pan and zoom.

- **Click a branch** to select it and open its action menu: ask the tutor about
  it, generate a quiz / exercises / flashcards / study guide from it (prefilled
  with the branch as the topic, the whole map as context), write a note, add it
  as a course node — or edit / add a child / delete the branch directly.
- The toolbar **⋯** menu works on the whole map: **AI edit mindmap** (expand /
  simplify / reorganize / add examples — with a live preview before applying),
  **Add root node**, **Quiz on this mindmap**, **Ask about this mindmap**, and
  **History…**.
- **History** lists every saved version (manual edits and AI edits alike). Pick
  one to preview it, then **Restore** to bring it back — restoring saves *as a
  new version*, so you can always undo the restore too.

## Creating things

Use the **+** button in the toolbar (or right-click the empty pane — same menu,
even when the folder has no materials yet):

- **New folder**, **New text file** / **New Markdown file** (opens the rich
  markdown editor — the same one notes use, with live math and diagram rendering;
  the file goes through the normal ingest pipeline and is immediately searchable),
  **Upload files…**, **Add linked folder…** (symlink to a real directory, see below).
- At the "All courses" root (right-click): **New course**.
- Inside a linked folder (right-click): **Refresh** only (the app never writes to a
  link's target).

Right-click a **material** for Open / Cut / Copy / Assign to node… / Rename / Delete
(deleting removes its extractions, search entries and assignments). Right-click a
**folder** for Open / Cut / Paste into folder / Rename / Delete; right-click a
**linked folder** for Open / Rescan / Reveal on disk / Rename / Unlink (links are
never move/copy targets).

**Renaming** opens a small editor that wraps long names over multiple lines and
grows as you type — press **Enter** to save, **Escape** to cancel, **Shift+Enter**
for a line break while thinking (line breaks are folded into spaces when saved,
since names stay single-line). In the grid view, titles show up to 3 lines and
reveal a 4th while the item is selected; list rows truncate to one line and
wrap to two when selected.

## Linked folders (symlinks)

A linked folder is a **symbolic link** in the tree (⧉ emblem) to a real directory
on disk — Nemo-style:

- Click it to browse the target **live**: subdirectories appear as you descend
  (nothing is copied or stored until you ingest); breadcrumbs show virtual path
  segments.
- Files not yet ingested show a dashed tile with a **pending** badge — click one to
  ingest it (or use **Ingest all** in the toolbar). Ingestion copies the content
  into the app so it survives even if the target disappears.
- **Rescan** reconciles the whole tree (new files become ingested materials on
  scan; changed files become new extraction versions; **files that moved or were
  renamed inside the target are recognized by content** — their history and
  reading progress stay intact).
- Scans also run automatically: shortly after the app starts and then every five
  minutes (configurable via `SA_SOURCE_SCAN_INTERVAL_SEC`).
- **Unlink** removes the link only — materials already ingested stay in the course;
  files on disk are never touched.
- If the target directory is gone (moved/deleted), the link shows **target
  missing** with a **Re-link** button — pick the new location with the folder
  picker.

### Choosing the target

Browsers never reveal absolute paths, so "Add linked folder…" opens the app's own
native-style picker with the **same breadcrumb bar as the Library** (`/ ▸ home ▸
you ▸ lectures` — click any segment to jump there) plus an Up button, a
double-click-to-open directory list, and a manual path box with Go. Press
**Choose** to link the current directory.

## Search

The search button (magnifier, top right) expands into a search box that
searches across all material **as you type** (Enter applies immediately, no
waiting for the debounce). When a course is open, results are scoped to that
course's library. Matching is typo-tolerant: misspelled words ("calclus",
"limts", "integraton") still find the right material, and exact matches rank
above fuzzy ones. With an embeddings model assigned it additionally combines
keyword and semantic matching; without one it is keyword-only. Results replace
the pane — click one to open the material page. Press **Esc** or clear the box
(and click away) to collapse it back to the icon.
