# Studio

**Studio** in the sidebar turns a chapter into a printable **slide deck** or
**handout**. It is a lens over your existing materials, not a second content
store: the generated artifact is also saved back into the course library as
markdown.

## Create an artifact

Choose a source material that already has extracted text, pick **Slide deck**
or **Handout**, and optionally give it a title. Studio builds a deterministic
outline from the material's headings:

- a title slide;
- one slide (or handout section) per heading;
- clean bullet points from the paragraphs under each heading.

No model is called and no web source is invented. If a chapter has no
headings, the paragraphs are chunked into slides. The result is capped at 20
slides and every bullet is short enough to present.

## Preview and print

Open an artifact to see the actual pages. **Print / PDF** uses the browser or
desktop print dialog:

- slide decks print at 16:9, one slide per page;
- handouts print at A4, one page per section;
- KaTeX math in bullets is rendered by the normal block renderer.

PowerPoint/Google Slides export is not supported; the print dialog is the PDF
path, as the control says.

## Library and lifecycle

Each artifact links back to its source material and to a generated markdown
material in the course library. Deleting the artifact keeps the generated
material; deleting the material leaves the artifact's spec intact. Reorder,
rich layout editing, research briefs and multi-artifact templates are still
planned.
