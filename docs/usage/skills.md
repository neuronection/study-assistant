# Skills & prompt library

Every AI behavior in the app (the tutor's hint ladder, quiz generation, the chat
answer, flashcard authoring, …) is a **skill**: a prompt template plus a **behavior
contract** (the rules that gate the output, like "never reveal the answer"). By
default these are the careful, tested prompts the app ships with — but you can read
them and, if you want, customize them.

**Settings → Skills** lists the skills and lets you manage **course types**.

## Reading and editing a skill

Open any skill. You'll see:

- **Scope** — where this edit applies: **System** (all courses), **Course type**
  (every course of that type, e.g. all math courses), or **Course** (one course).
  The most specific scope wins at runtime, and each scope shows its current
  version (a *v1* badge).
- **System template** — the model's instructions, with `{{variable}}` slots
  (click a variable chip to insert it).
- **User template** — an optional per-request wrapper.
- **Behavior contract** — the safe editable subset: max words, and the
  **no-answer-reveal** leak guard (keep it on unless you really know what you're
  doing). Novel rule kinds are code-only by design.
- **Test-run** — renders the template with sample context and lists the
  constraints that would be enforced, so you can see the effect without a live
  call.

## Saving, versions, restoring

Every **Save** creates a **new version** and activates it. The versions list lets
you activate any earlier one or **restore the system default** — code is always the
reset point. Each AI call records which skill version produced it, so behavior is
fully reproducible.

## Sharing

**Export pack** downloads the current skill (template + contract) as a JSON file;
**Import pack** loads one back into the editor. Paste-and-share between machines
(and with collaborators).

## Course types

Course types are scopes for skill overrides — e.g. a *math* type that biases the
tutor to Socratic, LaTeX-heavy hints. Add your own (e.g. *history*), then assign a
course to it (in the course's details). Skills resolved for that course then use
the type's override when one exists.
