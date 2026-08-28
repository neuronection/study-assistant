# Courses and outlines

A course structures your material into a tree of nodes — the course itself is the
root, and you can nest up to four levels below it.

## The course selector (current workspace)

The sidebar's course hub sits under the app name — the **logo tile** itself links
home. The switcher shows your *current course*, or a muted **Select a course**
placeholder when nothing is picked, and opens a popover listing every course with its
subject and material count. Courses are listed with a color-letter tile; when you
have more than five, a **search box** appears at the top (fuzzy matching on course
titles):

- Picking a course makes it the **current course** **and opens its workspace**
  (the app-side equivalent of its home screen).
- **All courses** (bottom of the popover) shows everything everywhere — quizzes,
  exercises, flashcards, notes, Anki decks are then not filed into one course.
  Useful for cross-course flashcard review.
- A **Courses** row opens the management page — the same page is also always in the
  nav below as a regular menu item.

With a course active, four shortcut buttons sit under the switcher in a 2×2 grid —
**Workspace · Materials · Notes · Practice** — jumping straight into that view of the
current course.

Being on a current course means:

- **Flashcards and Scores** show only that course's content, and everything you
  generate or import (quizzes, exercises, flashcards, notes, Anki decks) is filed
  into that course automatically — quizzes, exercises and notes live inside the
  course workspace (its **Practice**/**Notes** tabs). New chats from the sidebar
  also answer from that course's material.
- If you have no courses yet, the study surfaces show a hint to create one first —
  Library, Courses, Today and Settings are always available.

The selection is remembered per browser/profile and resets to "All courses" if the
course disappears (e.g. after switching profiles).

## Creating a course

**Courses → New course**. Give it a title and (optionally) a subject. Upload material
*into* the course from the Library — every material belongs to exactly one course,
and uploads always require one.

Each course card on the Courses page shows its title, subject, material count and —
when set — the course **description** (from the course settings popover in the
workspace header). When you have courses, a **search button** (magnifier icon,
top right) expands into a search box that filters courses by title, subject or
description as you type; press **Esc** or clear it to see all again.

## Deleting a course

Deleting a course removes **everything in it**: chapters and sections, materials
(with their extractions and search entries), the course's folder tree, notes,
quizzes, exercises, flashcards and chat sessions. The confirm dialog lists what goes;
there is no undo, so read it before confirming.

## Building structure

Structure is built and edited in the **structure sidebar** (right-click anywhere
in the panel):

- **Add child** inserts a node under any node (up to four levels below the course).
- **Rename** swaps the row for an inline input; **Delete** asks for confirmation —
  the node's children and material assignments move up to its parent.
- **Right-clicking anything that is not a row** — empty space, gaps, even the
  header and filter areas — applies the same menu to the node you are currently
  viewing, like a file manager acting on the open folder (**Add child** creates
  beneath it; without a node open it falls back to the course root). Only the
  search field keeps its native text menu for copy/paste.
- **Drag** a row onto another row to reparent it.
- No right-click handy? The **Overview** tab of any node creates children right
  from its **action bar** (the one with Compose / Review / Cheat sheet): an
  **Add child** button opens an inline title field beneath it. At the course root
  that bar instead shows **Add node** and **AI outline** — there is no separate
  Structure card.
- Or press **AI outline** on the root's *Overview* bar: the assistant reads your
  course materials' summaries and topics and drafts a node tree with objectives.
  **Nothing is saved until you commit** — remove nodes you don't want in the review
  card first.
- The AI also proposes which materials belong in each node (with a rationale and
  confidence). Accept them via the draft, or assign/remove materials manually from
  a node workspace's Materials tab via the **material catalog picker**: a
  Library-style browser with the course's folder tree in the sidebar, breadcrumb
  navigation, live fuzzy filtering, multi-select (or select a whole folder's
  subtree / everything shown in one click), already-assigned materials marked
  *Assigned here*, and linked folders you can open to pick from files that haven't
  been ingested yet (*Ingest & select* pulls them in on the spot). One **Assign**
  button allocates the whole selection to the node.
- You can also **assign a whole folder** (virtual or linked): the 📁+ button next
  to any folder row (sidebar or list, *Assign the whole folder* on hover) places
  the folder itself at the node. Its materials show a folder badge, and **files
  added to the folder later join the node automatically** — no re-assigning.
  Folders already assigned are marked with a lock.

### Materials tab

Assigned materials appear for the node. The header toggle switches between
**list** and **grid cards** (remembered per browser); grid tiles stay draggable
onto the structure sidebar to re-assign. The **search button** (magnifier icon)
next to it expands into a filter box that narrows the list by material or
folder name as you type.
Like the Library, a **single click selects**, a **double-click opens** a
material in its drawer, and **Enter** works too. **Drag across empty space to
rubber-band-select** — the rectangular marquee works exactly like the
Library's.
**Right-click** an assigned material to **Open** it, **Assign to node…** (move
it to another node), or **Remove from node** (or hover its ✕ in list mode).
Materials that arrive through an assigned folder carry a folder badge instead
of a per-file ✕ — to remove one, move the file out of the folder or
**Unassign folder** on the folder itself.

**Creating from here:** the **New…** button (or right-click on empty space)
opens the same create menu the Library uses — **New text file** / **New
Markdown file** (the rich editor, with live math and diagrams), **New folder**,
**Upload files…** and **Upload folder…**. New files are stored unfiled in the
course's library and assigned to this node right away (uploads behave the
same); the new-file dialog stays open after **Create** so you can keep writing
and **Save** again — **Done** closes it. A **New folder** is created at the
library root *and assigned to this node* — it appears as a folder tile at the
top of this list and its future contents join the node automatically.
**Assign material** opens the catalog picker.

**Multi-select works like a file browser**: click selects, Ctrl+click adds,
Shift+click ranges (folders select too). There is no selection banner — the
verbs live in the **right-click menu**: right-click any selected item and
**Unassign** removes the whole selection from this node (folder-derived
material rows are skipped), **Assign to node…** links the whole selection to
any node in the course tree. **Escape** clears the selection. Dragged rows
carry the whole selection, not just the row under the cursor — drop a
multi-selection onto a sidebar node to assign every material at once (the
drag image shows an "N items" badge).

**Assigned folders** sit at the top of the materials list as real **folder
tiles/rows** — a folder icon (linked-source folders carry a small link badge),
the folder name, and its member count. **Double-click a folder to open it in
the Library** at that folder; right-click it for **Open in library** /
**Unassign folder**, or hover the ✕ in list mode. An assigned folder is
selectable like a material (single click), so marquee and the selection bar's
**Unassign** / **Assign to node…** treat folders and materials alike; unassigning
a folder removes it from this node but keeps it in the course library.

## The node workspace

The course page *is* a workspace — the one for the course root. Every node in your
tree has the exact same workspace at `/courses/{id}/n/{nodeId}`, reachable via
breadcrumbs, the structure sidebar, child cards, or the command palette. Old
`/chapters/` links redirect there.

The header shows the breadcrumb (click any crumb to jump up the tree), the course
accent dot, a **structure sidebar** toggle, and two always-scoped actions:

- **Study here** — opens the **study launcher**: pick what the AI should do for
  this node (quiz, exercises, flashcards, study guide, summary sheet, practice set,
  error recap, mindmap, or write a note). Each action opens a generate form
  pre-scoped to the node, where you can fine-tune the scope and sources before
  running.
- **Ask about this node** — starts a tutor chat bound to this node and opens it
  in the **side panel** next to your workspace (its answers retrieve only this
  subtree's material). Use the ⤢ button in the panel header to expand it to the
  full chat page.

### The structure sidebar

The left panel shows the whole course as one tree — the course root on top, every
child node below it, nested to any depth. Click any row to jump to that node's
workspace (the active tab is preserved).

- The **current node** is highlighted; on first visit the tree auto-expands so
  it's always visible. Your open/closed choice — for the panel and every node —
  is remembered per course.
- Chevrons expand/collapse; **Expand all** / **Collapse all** sit under the
  header. The **Find a node…** box fuzzy-filters the whole tree into a match
  list.
- Each row shows small counters for what sits directly on that node — quizzes,
  exercises, notes (non-zero only, hover for details) — plus a **progress ring**
  (how many of the node's materials you've marked *studied*) and an amber
  **cards-due badge** when it has flashcards ready for review.
- **Right-click a row** to add a child, rename or delete the node. Deleting shows
  an **Undo** toast for a few seconds. **Drag** rows onto each other to reparent
  — or near a row's top/bottom edge to reorder siblings.
- Right-click also offers **Study…** — the same AI action menu the mindmap uses,
  scoped to that node: ask the tutor about it (chat bound to the node), generate
  a quiz / exercises / flashcards / study guide, or write a note. Generation
  opens the standard generate form prefilled to the node; finished quizzes and
  notes open automatically.
- Drag a material row from the node's Materials tab onto any sidebar node to
  assign it there.
- The tree is keyboard-navigable: click it, then ↑/↓ to move, →/← to expand and
  collapse, Enter to open.
- Virtualized, so even very large courses scroll smoothly. Hidden on narrow
  screens; toggle it with the panel button next to the breadcrumb.

Tabs (deep-linkable via `?tab=`). Every tab opens with the same **action bar**: one
primary action (filled) for the tab's main verb, outlined secondary actions beside it,
and tab meta (like the concept/graph counts) on the right. The same bar lives in the
same spot on every tab, so "where's the button" never depends on the tab you're on.

**Node settings** live in the workspace header, not in a tab: the gear next to the
node title opens a popover with the node's **Title**, **Description** (shown under
the title) and **AI instructions** (applied to every AI task in this subtree; course
root = whole course). The gear carries a small dot whenever custom AI instructions
are set. At the course root the Title/Description edit the course itself.

- **Overview** — objectives as chips, then the action bar: **Compose study material**
  (AI-assembled reading for this node), the AI **Review** and **Cheat sheet** actions,
  plus **Add child** (any node; inline title field below the bar) or, at the course
  root, **AI outline** (draft → review → commit) and **Add node**. Below the bar, a
  **Subsections** heading shows this node's children as cards (open, quick practice,
  ask; each card also shows its **description** when one is set); empty nodes prompt
  you to add the first subsection. Everyday tree editing
  happens in the sidebar.
- **Materials** — materials assigned directly to this node (reading-status pills,
  hover-× to unassign) plus **assigned folders** shown as folder tiles/rows
  (their member files stay **inside the folder** — they are not listed flat here;
  double-click a folder to open it in the Library and see its contents). The
  **New…** create menu (new text/Markdown files, new
  folder, uploads — see *Creating from here* above) plus an
  empty-state drop zone. **Dragging files or a folder onto the tab** (empty or
  not) opens an upload menu at the drop point — **Upload files…** for loose
  files, **Upload folder…** also offered when you drop a folder. Uploaded
  files are stored in the course's library and assigned to this node right
  away, then show their processing status as usual. Folder uploads keep their
  directory structure — the folder tree is recreated in the library (e.g.
  *Lecture pack/week1/…* becomes a real folder chain) and the **top-level folder
  is assigned to this node** (its contents join automatically as folder members,
  so the files aren't linked individually); junk files like `.DS_Store` are
  skipped automatically.
  **Assign material** opens the catalog picker (multi-select
  across folders, linked sources and un-ingested files) — the picker footer
  has its own upload button (uploads land in the folder you're
  browsing and are selected automatically), and its list keeps a
  drag-and-drop row.
  Clicking a material opens it **in place** as a
  drawer over the workspace (Extraction / Original / Side-by-side tabs, study
  state, assigned-to chips) — closing it returns to the same tab, and the URL
  gains `?material=<id>` so deep links and the back button work. The **⤢ /
  ⤡ button in the drawer header expands it to full width** (and back), handy for
  wide tables or side-by-side; your choice is remembered.
- **Notes** — this node's notes including everything below it (each row carries a
  chip showing which node owns it); **New note here** files the note at this node,
  **Draft notes** asks the AI to write one from the assigned material. Notes
  multi-select like the Materials tab and the Library: click / Ctrl+click /
  Shift+click plus **drag across empty space to rubber-band-select** — no
  selection banner. Right-click a selected note and, when several are selected,
  the menu acts on the whole selection: **Delete** (one confirm, trash-undo still
  works) and **Move to node…** (re-files every selected note at a picked node);
  right-clicking a lone note shows the single-item **Open** / **Rename** /
  **Move to node…** / **Delete** menu. **Right-click empty space on the Notes tab
  (even with no notes yet)** opens the same **New note here** / **Draft notes**
  actions as the toolbar. **Escape** clears the selection.
- **Concepts** — the **Extract concepts** bar action (graph summary on the right),
  then manage which concepts this node *covers* (cover/uncover toggles,
  add-coverage picker over the course graph) plus the full course graph below.
- **Practice** — quizzes and exercises rolled up over the subtree, each with a scope
  chip; **New practice** opens the unified builder and **Import** the quiz import
  dialog course-prebound. The list is multi-selectable: the selection bar gives
  **Delete** (trash snapshots — undo strips still appear) and **Move to node…**
  (re-scope the selection to any node; tree counters update).
  Below the action bar a two-way **segment switcher** splits this tab:
  - *Quizzes & exercises* (default): the rolled-up list, drills card, import.
  - *Flashcards*: the due-review queue plus every card in this subtree, with its own
    actions — **Generate**, Anki **Import .apkg / Export Anki deck**. Old
    `?tab=cards` links open here. The Practice tab itself shows live counts and,
    when cards are ready for review, an amber due badge.
- **Tutor** — the **Ask about this node** bar action (opens the side panel) plus
  chats bound to exactly this node; click one to reopen it in the sidebar.
- **Settings** (course root only) — two subtabs:
  - *General* — edit the course **title** and **description**; Save syncs the
    root node so breadcrumbs and lists follow.
  - *Tasks* — per-course **AI model overrides**. The *Default models* card sets
    the course-wide default per capability (text / image / embeddings): every
    task in this course without its own model uses it. The list below assigns
    specific models (and fallbacks) to single tasks for this course only, each
    select showing what it inherits when left empty.
  Resolution order per slot: global capability default → global per-task
  assignment → course capability default → course task assignment. Chapter
  nodes don't show this tab — overrides are a property of the whole course.

## Concepts (knowledge graph)

Press **Extract concepts** on a workspace's Concepts tab: the assistant reads your
materials' index cards and the outline, then proposes key concepts, relations
between them (requires / part of / related to) and which nodes cover each.
Review the draft — remove anything wrong with the × on a chip — then **Commit**.
Committing is additive: existing concepts are never overwritten, so you can
re-extract later to enrich the graph. Each concept shows its aliases, the
nodes that cover it, and its relations; the coverage card above the graph manages
which concepts the current node covers.

The **Review** action (workspace Overview tab) asks the AI organizer to look at the
node's children, assigned material and concept coverage and report honest findings:
gaps (material topics with no section), ordering problems, orphaned material, nodes
without coverage — each with a suggestion. Findings render inline **and** are saved
as a dated document ("… — Review 2026-08-21") in your library — re-running on
another day adds a new one, so you build an honest history; the Overview tab lists
past reviews as clickable chips.

**Cheat sheet** (the button is a menu in the workspace Overview tab) builds a
one-page formula/definition sheet for the node once material is assigned. With no
sheet yet, the menu offers **Generate cheat sheet…**; once one exists it offers
**Open existing** (opens the saved document) and **Regenerate cheat sheet…**. Both
generate options open the **compose builder** pre-configured for a cheat sheet —
you can shape the context (which materials to pull in or exclude, attach notes,
pick concepts, add one-time instructions) before generating, with a live preview of
what the AI will see. The result is **saved as a real document** — searchable,
editable (your edits are kept: regenerating *revises* the sheet and stores it as a
new restorable version instead of overwriting), printable, and visible to the AI
when you generate quizzes or ask the tutor. Repeated generation never piles up
files: one sheet per node, regenerate = new version.

**Formula sheet** (study launcher at the course root) assembles every formula
found across your notes — including transcribed handwriting — and material into
one printable sheet; the AI may only organize what it collected, never invent
entries.

## Exam dates

Set an **exam date** in the course header's settings popover (root node). Courses
with an exam within 30 days show a **countdown card on the Today screen** —
coverage of studied nodes, a rough pace line ("≈2 nodes/day to finish") and a
one-tap jump to the first node you haven't touched.

## Study states

Materials can be marked unread / reading / studied per profile — a cheap signal that
will feed mastery estimates and recommendations.
