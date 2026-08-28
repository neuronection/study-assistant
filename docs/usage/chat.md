# Tutor chat

The chat sidebar (message icon, bottom-left) answers questions about your material.
**Ask about this node** in a workspace also opens the sidebar, pinned to a chat
bound to that node; the ⤢ button expands it to the full page, and collapsing the
full page (⤡) carries that conversation back into the sidebar.

## Attaching items (the + button)

The **+ button** next to the message box opens an attach menu. Three quick
actions sit above the tabs: **Insert equation…** (LaTeX with live preview,
inserted at the cursor), **Open drawing canvas…** (sketch a problem or diagram —
it uploads to the *Chat uploads* folder and attaches as a material), and
**Capture screenshot…** (pick a window or screen, drag a rectangle, attach the
crop — requires running in a browser, not the desktop shell). Below them, six
tabs:

- **Materials** — your course library (scoped to the chat's course when it has one).
- **Notes**, **Quizzes**, **Exercises** — search by title and pick one.
- **Courses** — attach any course; it resolves to the course itself (title +
  description) so the tutor can discuss it.
- **Upload a file** — pick a file from your computer: it is saved into that
  course's library under a *Chat uploads* folder and ingested like any other
  material (OCR, extraction, indexing). Once processing finishes the tutor can
  read it; before that it will tell you the file isn't ready yet.

Uploads are organized per conversation: each chat gets its own subfolder of
*Chat uploads* named after the session (e.g. `New chat (#4)`), and drawings and
screenshots are numbered per folder (`Drawing 1.png`, `Screenshot 2.png`, …).
The folder is created with the conversation — uploading before sending any
message creates the chat — and if you rename the conversation, the folder is
renamed to match on the next upload.

Attached items show as chips above the input (removable with their ✕). When you
send, the chips are handed to the tutor as reference handles: it sees them in its
offer list, mentions them as clickable cards, and can **READ** any of them in
full — including whole quizzes (questions, options, correct answers) and
exercises (steps with expected answers). Uploads need a course target: a
course-bound chat files into that course; a course-less chat falls back to the
**Unsorted** course (or your only course) and the dialog tells you where the
file lands. With no course to fall back to, uploads, drawing and screenshot are
unavailable.

## Dictation

Instead of typing, click the **🎤 button** in the message box, speak your
question, and click **Insert** — the transcript drops into the composer at the
cursor, ready to edit and send. A small strip with a timer and a live level
meter appears while you speak; **Cancel** (✕) discards the recording without
transcribing. Transcription uses the speech-to-text model assigned to the
*Transcribe* task (Settings → AI → Tasks) — the same model the note editor's
dictation uses — and your browser will ask for microphone permission once.

## Grounded answers with citations

Answers that make claims about your course material cite it: `[1]`, `[2]` markers
map to chips under the answer showing which document (and passage) supports them.
If a chat session is tied to a course, only that course's material is searched.

Answers that could not be grounded in your material are marked
*"Not grounded in your material"* so you know what to trust.

## Clickable item cards

When the tutor refers to something from your course — a document, one of your
notes, a concept, or a course section — the reference appears as a **clickable
chip** with an icon. Click it to jump straight to that item: documents open in
the library, notes in the note editor, concepts in the workspace Concepts tab,
sections in their workspace. Every chip refers to something that actually exists
in the course; the tutor is only allowed to reference items it was shown.

## Action proposals (you approve, then it happens)

When it clearly helps, the tutor can end a reply with a **proposal card** — for
example *create a note* with a summary it just wrote, *assign a material* to
the section you're discussing, *cover a concept* there, set the section's AI
instructions, or *generate a quiz/exercise*. Nothing happens until you click
**Approve**; you can expand the card to preview exactly what would happen, or
**Dismiss** it.

Two special cases:

- **Generate proposals** open the generator dialog **prefilled** with the
  suggested settings when approved — nothing is generated until you click
  Generate in the dialog.
- If the world changed since the proposal (a section was deleted, a material
  removed), approving marks the card **Out of date** with the reason instead
  of doing something wrong.

Approved notes land in the course workspace (tagged as AI-proposed) and the
card links straight to them. If you dismiss a couple of proposals, the tutor
notices and becomes more conservative about proposing.

## What the AI sees

The **What the AI sees** panel (book icon, under the session picker) shows the
context offered to the tutor: the scope section for course-bound chats, the
notes it automatically considers, and every item it may reference or read.
Nothing is hidden — this is exactly the offer list.

The tutor can **READ** an offered item in full when the retrieved excerpt isn't
enough (a whole document, one of your notes). When it does, an eye-icon chip
appears under the answer marking what was read — the fetched content itself
stays out of the conversation.

## Math verification

The chat can run exact math tools before answering (deriving, solving, simplifying).
Every tool it runs shows as a **tool card** under the reply — a small line naming
the tool (e.g. `CALC`, `SYMPY`, `READ`, `PLOT`) and what it was called with. Click
a card to expand it and see the full argument and (for math tools) the exact result,
computed by a real algebra system rather than guessed.

## Tools

The **wrench button** in the chat header opens the tool catalog: every tool the AI
can use, one card per tool — what it does, its arguments (name, type, required),
what it returns, and its scope. Two groups:

- **Chat math tools** — CALC (numeric evaluation) and SYMPY (solve, simplify,
  diff, integrate, expand, factor, limit), the sandboxed verifiers the tutor runs
  before asserting math.
- **Reading tools** — READ fetches an offered item's full content on demand
  (up to 3 per turn, char-budgeted).
- **MCP resource tools** — the seven read-only tools external AI agents can call
  through `python -m studyassistant mcp` (course listing, node overview,
  materials, concepts, exercises, quizzes, notes). The chat itself doesn't call
  these; they're listed so you can see what an connected agent could read.

## Streaming

Answers stream in token by token with live math rendering; while you wait for
the first words, an animated three-dot indicator shows the tutor is thinking.
The message box grows with your text (Enter sends, Shift+Enter adds a line), and
an empty chat opens with a few starter prompts.

## Sessions

Clicking the chat icon always opens a **new chat**: you can type, attach items
and send right away — the session itself is only created on the backend when
your first message is sent (titled from that message). Nothing is saved if you
just peek and close. Pick up earlier chats from the dropdown, or press **+** to
discard the current draft and start fresh. The **⋯ button** next to the
dropdown renames or deletes the active chat (deleting removes all its
messages).

## When a reply fails

If the tutor's task fails (for example no model is assigned to the *chat* task,
or the provider is unreachable), the panel shows a red **"The tutor failed to
answer"** banner with the underlying error instead of spinning forever — your
message stays in the conversation and you can simply send it again after
fixing the cause (check Settings → Tasks for unassigned models). A stalled
turn also times out after 90 seconds with the same banner.
