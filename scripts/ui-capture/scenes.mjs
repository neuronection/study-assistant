/**
 * UI capture scene catalog for Study Assistant (repo-owned; the
 * family-standard sync script never overwrites this file).
 *
 * Captures run against a demo instance served by the backend in webapp
 * mode (single origin on :8200) — see docs/dev/visual-tour.md for the
 * boot recipe. Pages use plain h1 headings as ready anchors.
 *
 * The chat scene drives the demo scripted tutor on purpose: the prompt
 * triggers a canned study answer with KaTeX math, a Plotly chart, a
 * flashcard-deck proposal card and grounded citations — rendered items,
 * not just prose.
 */
export const groups = [
  "Authentication",
  "Study loop",
  "Material",
  "Progress",
];

export const scenes = [
  {
    name: "login",
    group: "Authentication",
    caption: "Sign-in overlay — cookie-session auth over the Today screen.",
    narration: "Sign in — your courses, notes and review schedule are waiting.",
    path: "/",
    auth: false,
    fullPage: false,
    viewports: ["desktop"],
    waitForSelector: "form",
  },
  {
    name: "today",
    group: "Study loop",
    caption: "Today screen — the daily study dashboard.",
    narration: "Today greets you with what matters: due reviews, goals and where you left off.",
    path: "/",
    viewports: ["desktop"],
    waitForSelector: "h1",
  },
  {
    name: "courses",
    group: "Study loop",
    caption: "Courses — the student's course list.",
    narration: "Every course holds its own tree of chapters, materials, notes and practice.",
    path: "/courses",
    viewports: ["desktop"],
    waitForSelector: "h1",
  },
  {
    name: "course-detail",
    group: "Study loop",
    caption: "Course detail — chapters, materials and study actions.",
    narration: "Open a course to see its structure at a glance.",
    path: "/courses/{courseId}",
    viewports: ["desktop"],
    waitForSelector: "h1",
  },
  {
    name: "node-workspace",
    group: "Study loop",
    caption: "Node workspace — the rich-text editor with notes and materials for a chapter.",
    narration: "The workspace is where studying happens — notes in a rich editor, materials side by side.",
    path: "/courses/{courseId}/n/{nodeId}",
    interactions: [
      { action: "wait", ms: 1500 },
    ],
    viewports: ["desktop"],
    waitForSelector: "h1",
  },
  {
    name: "study-session",
    group: "Study loop",
    caption: "Guided study session — the focused flow across review and practice.",
    narration: "Or let the study session drive — review, practice and recall in one guided loop.",
    path: "/study/session",
    viewports: ["desktop"],
    waitForSelector: "h1",
  },
  {
    name: "library",
    group: "Material",
    caption: "Library — every ingested material, searchable.",
    narration: "The library keeps every ingested document searchable.",
    path: "/library",
    viewports: ["desktop"],
    waitForSelector: "text=All courses",
  },
  {
    name: "material-detail",
    group: "Material",
    caption: "Material detail — the extraction view over an ingested document.",
    narration: "Each material is parsed into a structured extraction you can study from.",
    path: "/library/{materialId}",
    viewports: ["desktop"],
    waitForSelector: "h1",
  },
  {
    name: "review",
    group: "Study loop",
    caption: "Review — FSRS-scheduled flashcards due today.",
    narration: "Spaced repetition decides what comes back and when.",
    path: "/review",
    viewports: ["desktop"],
    waitForSelector: "h1",
  },
  {
    name: "review-revealed",
    group: "Study loop",
    caption: "Review — a flashcard with the answer revealed and FSRS ratings.",
    narration: "Reveal, rate — again, hard, good, easy — and the scheduler learns.",
    path: "/review",
    interactions: [
      { action: "click", selector: "text=Show answer" },
      { action: "waitFor", selector: "text=Again", timeout: 10000 },
    ],
    settleMs: 1000,
    viewports: ["desktop"],
    waitForSelector: "h1",
  },
  {
    name: "chat",
    group: "Material",
    caption: "Tutor chat — a demo study answer with math, a recall chart and a flashcard-deck proposal card.",
    narration: "Ask the tutor for flashcards — the answer arrives with the math, your recall trend and a deck proposal to approve.",
    path: "/chat",
    interactions: [
      { action: "fill", selector: "textarea", value: "Make me flashcards for vector spaces and show my recall trend" },
      { action: "press", key: "Enter" },
      { action: "wait", ms: 6000 },
    ],
    viewports: ["desktop"],
    waitForSelector: ".katex",
  },
  {
    name: "scores",
    group: "Progress",
    caption: "Scores — performance across quizzes, exercises and reviews.",
    narration: "Scores turn all that effort into a trend you can steer by.",
    path: "/scores",
    viewports: ["desktop"],
    waitForSelector: "h1",
  },
  {
    name: "settings",
    group: "Progress",
    caption: "Settings — profiles, AI providers and preferences.",
    narration: "Everything is configurable — profiles, AI providers, privacy.",
    path: "/settings",
    viewports: ["desktop"],
    waitForSelector: "h2",
  },
];
