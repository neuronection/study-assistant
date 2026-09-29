# Troubleshooting

Most problems come down to an unconfigured AI provider, a background job that
failed, or a data-directory surprise. This page walks through the common ones.
If something here does not match what you see, check the
[known-issues section of STATUS.md](../STATUS.md) and open an issue on
[GitHub](https://github.com/neuronection/study-assistant/issues).

## AI features do nothing / "no model assigned"

The app starts unconfigured on purpose — AI features return an error until you
connect a provider and assign models.

1. Open **Settings → AI → Providers** and add a provider (or run the setup
   wizard from the Home onboarding card).
2. Go to **Tasks** and set at least one default model per capability you use:
   **text** for chat/quiz generation, **vision** for OCR, **embeddings** for
   semantic search, **speech-to-text** for dictation.
3. If a key was rejected, nothing was saved — re-check the key or try the
   provider's **Test** button.

See [Settings reference](settings.md) and [Local AI](local-ai.md).

## OCR produced nothing useful

- Confirm a **vision-capable** model is assigned to the OCR task (the dropdown
  only offers vision models; if none are listed, add one under Models).
- For scans with a poor text layer, re-run extraction and choose OCR explicitly
  from the material's ⋯ menu → **Re-extract**.
- Very large images are downscaled before OCR (Settings → Search & OCR); raise
  the long-edge cap if fine detail is being lost.

## An upload was refused

Unknown file types are rejected at the door with a reason. Convert the file to a
supported format (PDF, image, Markdown, DOCX/PPTX/EPUB/HTML, audio/video) or
check the accepted-types list shown in the picker. Uploads are capped at 200 MB.

## Background work is stuck or failed

Open the **Activity** page (`/jobs`). Failed jobs show an error and, where the
job type supports it, a **Retry** button; **Retry failed** retries them all. A
job left `running` by a crash is reclaimed as failed on the next start and can
be retried. See [Task activity and retries](activity.md).

## The desktop window is blank

This is a WebKitGTK rendering issue on some drivers. Try, in order:

1. Run `pnpm webapp` — the browser mode is the recommended fallback and uses the
   same data.
2. Open **Settings → Developer** and run the rendering check; the shell
   normally falls back to software rendering automatically on Linux.
3. See [Desktop app](desktop-app.md) and the STATUS known-issues list.

## My database (and providers) seem to have vanished

If you launch from a sandboxed terminal such as the VS Code snap, it can rewrite
`XDG_DATA_HOME` to a version-specific path, so a snap update points the app at a
new empty folder. Your keyring entries are safe, but the database now lives
elsewhere. Pin a stable data directory by creating `backend/.env`:

```ini
SA_DATA_DIR=/home/<you>/.local/share/StudyAssistant
```

See [Getting started](getting-started.md) for the working-directory rules.

## Search misses things / no semantic results

Semantic search needs an **embeddings** model assigned to the `embeddings` task.
Without it, search falls back to keyword-only (FTS + fuzzy) and still works. To
enable semantic search, assign an embeddings model in Settings → AI → Tasks.

## Backup or restore problems

- Backups land in `backups/` in your data directory; Settings → Data lists them
  and can restore, download or delete each one.
- To move to a new machine, download a backup, set the working directory on the
  new machine, then restore the backup into it.
- If the database is ever found corrupt at startup, the app quarantines it and
  restores the newest valid backup automatically; the recovery is reported in
  Settings → Data. See [Backups, trash & restore](backup.md).

## A deleted item is missing

Deleted materials and topics go to the **trash** (Settings → Data) before they
are purged. Restore from there, or empty the trash to remove them for good.
Restoring a material also rebuilds its search index; restoring a topic brings
its subtree back under the nearest surviving parent.

## Printing or PDF export looks wrong

Use the app's print action rather than the browser's own menu so math and
diagrams render correctly; the print stylesheet is what makes KaTeX and figures
come out right. See [Printing & PDF export](printing.md).

## Getting more detail

Backend and job errors are visible on the Activity page and in the terminal you
launched the app from. When reporting a bug, include the exact error text and
what you were doing — it makes the issue reproducible.
