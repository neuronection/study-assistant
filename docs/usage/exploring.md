# Exploring topics — the Scratchpad

The Scratchpad is your playground. It is a private, hidden course that belongs
to you (not to any subject) where you can capture ideas, take notes, upload
files, and chat with the tutor about anything — before you ever commit to
building a real course. Everything you already know works there: notes with
drawings, text/Markdown files, chat uploads, reading status, and all AI
actions.

## Where to find it

- The **Home** page has an **Explore a topic** button that opens your
  Scratchpad.
- Once the Scratchpad has content, a **Scratchpad** row appears in the left
  rail (under the course switcher). It stays hidden while it is empty.
- Chat uploads land in the Scratchpad automatically when a chat is not bound
  to a course.

Inside, organize freely: add child nodes to build a small topic tree ("Group
theory" → "Cyclic groups"), park notes on them, attach files, and ask the
tutor. Scratchpad activity still counts toward your streaks and daily goals —
but it never pollutes course analytics: exam forecasts and Today's course
recommendations ignore it, so exploration can't masquerade as course progress.

## Promote to course

When a scratch topic grows into something you want to study seriously:

1. Right-click the topic's node in the workspace tree (inside the Scratchpad).
2. Choose **Promote to course…**.
3. Name the course (and optionally set subject and level), then **Create
   course**.

The whole subtree moves — nodes, subtopics, notes, files, and chat bindings —
and becomes a normal course. Nothing is copied or regenerated; the Scratchpad
is empty again. One honest exception: **concept coverage stays behind**
(concepts are per-course), so rebuild coverage in the new course when you add
material.

## Generate a course from a topic (course genesis)

When you know the subject but have no material yet, use **Generate a course
from a topic** on the Home page:

1. **Describe the topic** — "Linear algebra for economists", optionally with a
   level (school, university-intro, university-advanced). Press **Draft
   outline**.
2. **Review the outline** — the AI drafts a two-level course (chapters with
   sections and learning objectives). Edit the course and section titles until
   it looks right; nothing exists yet.
3. **Pick what to generate** — a **lesson** per chapter, a short **quiz** per
   chapter, and **flashcards** per chapter. The dialog shows the estimated
   number of generation tasks; the run is budget-capped so it can never run
   away. Press **Create course**.

The course is created immediately and the generation runs in the background
(one failed task never blocks the rest — retry anything that failed from the
activity rail). Everything lands as normal, editable, AI-tagged content, and
the course honestly prompts you to **add your own material** — genesis is a
starting scaffold, not a textbook replacement.

## Research tools on the web

If a **web search provider** is configured (Settings → Providers → Web search —
any Tavily-compatible endpoint or a SearXNG instance; the API key lives in your
system keyring), the tutor gains two research tools:

- **SEARCH** — runs a web search and shows the top results as clickable source
  chips on the tool card. Ask about current or contested topics and the tutor
  can ground its answer in what it finds (it is asked to cite the sources it
  uses). Up to two searches per message.
- **FETCH** — reads one specific page you or the tutor picked, as plain text
  (up to 4 000 characters). One per message.

Search content is never stored — only the source links remain visible on the
tool cards. Without a provider, the tutor simply says web search is not
configured, and the genesis dialog hides its web-grounding option; with one,
"Generate a course" gains a **Ground the outline in web sources** checkbox and
grounded courses remember their sources in the course description.
