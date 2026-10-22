# Discovering material

**Discover** finds study material outside your library and keeps a list of what
you found. Nothing is imported until you choose to attach it — discovery is a
suggestion funnel, never an auto-import (ADR-167).

Open it from a course or node workspace (**Discover material**). Search a topic,
then narrow the providers with the chips above the results.

## Providers

| Provider | What it finds | Key needed |
|---|---|---|
| **Web** | general web results through your configured search provider | depends on that provider |
| **YouTube** | videos matching the topic | no |
| **arXiv** | preprints and papers (Atom API) | no |
| **OpenAlex** | papers, books and datasets with DOI metadata | no |
| **Crossref** | DOI metadata (fallback when OpenAlex is unavailable) | no |
| **Site presets** | results restricted to a domain (Khan Academy, Wikipedia, MIT OCW, OpenStax) | your search provider |
| **MCP connectors** | tools you connected that speak the discovery contract | per connector |

Scholar results carry their citation metadata (authors, year, DOI, container,
kind) into the saved suggestion, so attaching one creates a link material with
that metadata already filled in. The three scholarly providers are key-free and
enabled by default; choose them in **Settings → Tools → Discovery** like any
other provider.

## Suggested, saved, dismissed

Every result you act on becomes a suggestion in one of three states:

- **Suggested** — tracked but not attached.
- **Saved** — kept for later (the bookmark action). Attaching later creates the
  material.
- **Dismissed** — hidden from the results for that topic; restore it from the
  *Saved & dismissed* section.

The same section shows the suggestion's material once you attach it. Attaching
an already-saved URL creates a **link material** in the selected course; the
per-course URL dedupe means re-saving the same paper never creates a second
material.

## Importing a result

- **Attach as link** (paper, article, reference) — creates the link material
  immediately, citation metadata included.
- **Import & parse** (pages, videos) — creates the link and runs the parser for
  that URL (readable content, transcript, or file), then ingests it.

Discovery results themselves are never stored in the chat transcript or the
library; only the suggestion row and the material you choose to create.
