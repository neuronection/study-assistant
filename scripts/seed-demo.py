#!/usr/bin/env python
"""Seed synthetic demo data into a Study Assistant **demo** instance (S8).

Demo data (synthetic user content) may only be seeded by this explicit
script, only on a `demo_mode=true` instance, only into the demo database
(`neuro_study_demo`) / an isolated demo data dir (identity-auth §13,
deployment.md). **The seeder refuses anything else** — loudly, non-zero:

* target guard: a PostgreSQL target must be a database named `*_demo`;
  a SQLite target must sit inside an explicitly named `--demo-dir`
  (the isolated demo data dir). Anything else is refused before the
  database is touched.
* instance guard: `instance_settings.demo_mode` must be `true`.
  `--init-demo` may initialize it — but only on an EMPTY demo database
  (no `instance_settings`, `users`, `profiles` or `courses` rows);
  anything else is refused.

Reference data is not demo data: the startup catalogs (course types,
skills, error patterns) and the in-app sample course stay untouched —
this script only *ensures* the course-type catalog exists.

Usage (interpreter with the app's dependencies, e.g. `.venv/bin/python`):

    # PostgreSQL demo database (the docker demo flavor):
    SA_DATABASE_URL=postgresql+psycopg://user:pass@db:5432/neuro_study_demo \\
        python scripts/seed-demo.py

    # Isolated demo data dir (SQLite), first run on an empty database:
    python scripts/seed-demo.py --demo-dir /srv/study-demo/data --init-demo

    # Reset the demo workspace to its pristine synthetic state, then reseed:
    python scripts/seed-demo.py --demo-dir /srv/study-demo/data --reset

Flags: `--database-url` (else `SA_DATABASE_URL`, else the `SA_DB_*`
Settings — URL wins per deployment.md), `--demo-dir`, `--init-demo`,
`--reset`. The run is idempotent: re-running changes no counts.

The seeded workspace is synthetic-only — clearly fictional users, study
profiles, courses, materials, notes and flashcards. The demo users share
the documented demo password `DemoStudy!2026`; on demo instances the
credential-free `demo` principal (POST /api/v1/auth/demo) works as well.

Exit codes: 0 seeded (or already seeded), 2 refused by a guard rail,
1 unexpected error.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete, func, inspect, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.domain.models import (  # noqa: E402
    AuthSession,
    Chunk,
    Course,
    CourseType,
    Exercise,
    ExerciseStep,
    Extraction,
    FsrsState,
    InstanceSetting,
    Material,
    MaterialIndexCard,
    MaterialLink,
    MaterialStudyState,
    Note,
    NoteVersion,
    Profile,
    TreeNode,
    User,
    utcnow,
)
from app.pipelines.ingest import _store_extraction  # noqa: E402
from app.services.content.drawings import md_to_blocks, note_search_text  # noqa: E402
from app.services.content.materials import detect_kind  # noqa: E402
from app.services.content.notes import normalize_tags  # noqa: E402
from app.services.knowledge.tree import TreeService  # noqa: E402
from app.services.platform.skills import seed_course_types  # noqa: E402
from app.services.study.cards import create_card_exercise, front_title  # noqa: E402
from app.storage.blobs import BlobStore  # noqa: E402
from app.storage.db import make_engine, make_session_factory  # noqa: E402
from app.storage.fts import sync_material_fts  # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2

DEMO_PASSWORD = "DemoStudy!2026"
DEMO_NAMESPACE = uuid5(NAMESPACE_URL, "https://demo.study-assistant.invalid/seed")
DEMO_PRINCIPAL_ID = "00000000-0000-4000-8000-00000000d0e0"


class Refusal(Exception):
    """A guard rail refused the run — print loud, exit non-zero."""


def demo_id(kind: str, key: str) -> str:
    return str(uuid5(DEMO_NAMESPACE, f"{kind}:{key}"))


# --------------------------------------------------------------------------
# Synthetic fixture — clearly fictional people and study content only.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CardSpec:
    front: str
    back: str
    kind: str = "basic"
    due_in_days: int = 0


@dataclass(frozen=True)
class MaterialSpec:
    filename: str
    title: str
    markdown: str
    summary: str
    topics: tuple[str, ...]
    key_terms: tuple[str, ...]
    reading_minutes: int = 12
    difficulty: int = 2
    study_status: str = "unread"
    study_progress: float = 0.0
    chapter: str = ""


@dataclass(frozen=True)
class NoteSpec:
    title: str
    body_md: str
    tags: tuple[str, ...] = ()
    chapter: str = ""


@dataclass(frozen=True)
class CourseSpec:
    title: str
    description: str
    subject: str
    level: str
    course_type: str
    color: str
    exam_date: str
    goals: tuple[str, ...]
    tags: tuple[str, ...]
    chapters: tuple[str, ...] = ()
    materials: tuple[MaterialSpec, ...] = ()
    notes: tuple[NoteSpec, ...] = ()
    cards: tuple[CardSpec, ...] = ()


@dataclass(frozen=True)
class ProfileSpec:
    key: str
    name: str
    color: str
    courses: tuple[CourseSpec, ...] = ()


@dataclass(frozen=True)
class UserSpec:
    key: str
    full_name: str
    email: str
    is_admin: bool = False
    profiles: tuple[ProfileSpec, ...] = ()


LINEAR_ALGEBRA = CourseSpec(
    title="Linear Algebra",
    description=(
        "Vectors, matrices and linear maps. Weekly problem sets plus a "
        "proof-heavy midterm — the fictional course that anchors this demo."
    ),
    subject="Mathematics",
    level="Year 1",
    course_type="math",
    color="#4f7cff",
    exam_date="2026-12-15",
    goals=("Fluent with matrix algebra", "Write short epsilon-free proofs"),
    tags=("matrices", "proofs", "vectors"),
    chapters=("Vector spaces", "Matrix calculus"),
    materials=(
        MaterialSpec(
            filename="01 — Vector spaces primer.md",
            title="01 — Vector spaces primer",
            markdown=(
                "# Vector spaces primer\n\n"
                "A **vector space** $V$ over a field $F$ is a set with addition "
                "and scalar multiplication satisfying the eight usual axioms "
                "(associativity, distributivity, …).\n\n"
                "## Standard examples\n\n"
                "- $\\mathbb{R}^n$ with component-wise operations\n"
                "- Polynomials of degree $\\le n$\n"
                "- Continuous functions on $[0, 1]$\n\n"
                "## Subspace test\n\n"
                "A subset $U \\subseteq V$ is a subspace iff it is non-empty and "
                "closed under addition and scalar multiplication.\n"
            ),
            summary="Axioms, examples and the subspace test for vector spaces.",
            topics=("vector spaces", "subspaces", "axioms"),
            key_terms=("vector space", "subspace", "closure", "field"),
            study_status="read",
            study_progress=1.0,
            chapter="Vector spaces",
        ),
        MaterialSpec(
            filename="02 — Matrix multiplication notes.md",
            title="02 — Matrix multiplication notes",
            markdown=(
                "# Matrix multiplication notes\n\n"
                "For $A \\in \\mathbb{R}^{m \\times n}$ and "
                "$B \\in \\mathbb{R}^{n \\times p}$ the product $AB$ has entries "
                "$(AB)_{ij} = \\sum_k A_{ik} B_{kj}$.\n\n"
                "## Pitfalls\n\n"
                "- $AB \\neq BA$ in general.\n"
                "- $AB = 0$ does not imply $A = 0$ or $B = 0$.\n\n"
                "## Transpose rule\n\n"
                "$(AB)^{\\mathsf{T}} = B^{\\mathsf{T}} A^{\\mathsf{T}}$ — the order "
                "reverses.\n"
            ),
            summary="Mechanics and pitfalls of matrix multiplication.",
            topics=("matrices", "transpose"),
            key_terms=("matrix product", "transpose", "non-commutative"),
            study_status="reading",
            study_progress=0.5,
            chapter="Matrix calculus",
        ),
    ),
    notes=(
        NoteSpec(
            title="Seminar notes — week 3",
            body_md=(
                "# Seminar notes — week 3\n\n"
                "Dr. Halvorsen worked through the **subspace test** on two "
                "counter-examples. Takeaway: closure under addition alone is not "
                "enough — check scalar multiplication too.\n\n"
                "## Questions for next week\n\n"
                "- Does every vector space have a finite basis?\n"
                "- How does dimension behave under quotients?\n"
            ),
            tags=("seminar", "week-3"),
            chapter="Vector spaces",
        ),
        NoteSpec(
            title="Proof patterns I keep forgetting",
            body_md=(
                "# Proof patterns I keep forgetting\n\n"
                "- To show linear independence: start with "
                "$\\sum a_i v_i = 0$ and derive $a_i = 0$.\n"
                "- Dimension argument: a spanning set of size $n$ is a basis "
                "iff the space has dimension $n$.\n"
            ),
            tags=("proofs", "revision"),
        ),
    ),
    cards=(
        CardSpec("What are the two closure axioms of a subspace?", "Closure under addition and closure under scalar multiplication", due_in_days=-1),
        CardSpec("State the transpose rule for a matrix product.", "$(AB)^{\\mathsf{T}} = B^{\\mathsf{T}} A^{\\mathsf{T}}$", due_in_days=0),
        CardSpec("Does $AB = 0$ imply $A = 0$ or $B = 0$?", "No — non-zero matrices can multiply to zero.", kind="reverse", due_in_days=2),
        CardSpec("A non-empty subset closed under addition and scalar multiplication is …", "a subspace", kind="cloze", due_in_days=5),
    ),
)

DATABASES = CourseSpec(
    title="Databases I",
    description="Relational modelling, normal forms and SQL — fictional second-year course.",
    subject="Computer Science",
    level="Year 2",
    course_type="programming",
    color="#2f9e6e",
    exam_date="2027-01-18",
    goals=("Normalise a schema to 3NF", "Write joins without second-guessing"),
    tags=("sql", "normalization"),
    chapters=("Relational model",),
    materials=(
        MaterialSpec(
            filename="01 — Normal forms cheat sheet.md",
            title="01 — Normal forms cheat sheet",
            markdown=(
                "# Normal forms cheat sheet\n\n"
                "## 1NF\n\n"
                "Atomic values only — no repeating groups.\n\n"
                "## 2NF\n\n"
                "1NF and no partial dependency on part of a composite key.\n\n"
                "## 3NF\n\n"
                "2NF and no transitive dependency of a non-key column on the "
                "key. Rule of thumb: every non-key attribute depends on "
                "*the key, the whole key, and nothing but the key*.\n"
            ),
            summary="1NF → 2NF → 3NF with the classic one-line rule.",
            topics=("normalization", "3NF"),
            key_terms=("1NF", "2NF", "3NF", "transitive dependency"),
            chapter="Relational model",
        ),
    ),
    notes=(
        NoteSpec(
            title="ER modelling questions",
            body_md=(
                "# ER modelling questions\n\n"
                "- When is a join table preferable to an array column?\n"
                "- How do we model a *required* one-to-one relation?\n"
            ),
            tags=("modelling",),
            chapter="Relational model",
        ),
    ),
    cards=(
        CardSpec("State the one-line rule for 3NF.", "Every non-key attribute depends on the key, the whole key, and nothing but the key.", due_in_days=1),
        CardSpec("What does 1NF forbid?", "Repeating groups and non-atomic values.", due_in_days=3),
        CardSpec("A partial dependency violates …", "2NF", kind="cloze", due_in_days=6),
    ),
)

GREEK_A2 = CourseSpec(
    title="Modern Greek A2",
    description="Evening class: past tense, daily vocabulary, spoken practice.",
    subject="Languages",
    level="A2",
    course_type="language",
    color="#e2725b",
    exam_date="2027-05-22",
    goals=("Handle past-tense narration", "500 active words"),
    tags=("vocabulary", "grammar"),
    chapters=("Past tense",),
    materials=(
        MaterialSpec(
            filename="01 — Past tense verbs.md",
            title="01 — Past tense verbs",
            markdown=(
                "# Past tense verbs\n\n"
                "The perfective past («αόριστος») is built from the aorist stem: "
                "«έγραψα, έγραψες, έγραψε» …\n\n"
                "## Common irregulars\n\n"
                "- «πάω» → «πήγα» (I went)\n"
                "- «βλέπω» → «είδα» (I saw)\n"
                "- «τρώω» → «έφαγα» (I ate)\n"
            ),
            summary="Aorist stems and the three irregular verbs that matter at A2.",
            topics=("past tense", "verbs"),
            key_terms=("αόριστος", "aorist", "irregular verbs"),
            study_status="reading",
            study_progress=0.3,
            chapter="Past tense",
        ),
    ),
    notes=(
        NoteSpec(
            title="Phrases to practise out loud",
            body_md=(
                "# Phrases to practise out loud\n\n"
                "- «Χθες πήγα στη βιβλιοθήκη και διάβασα δύο ώρες.»\n"
                "- «Τι έκανες το σαββατοκύριακο;»\n"
            ),
            tags=("speaking",),
            chapter="Past tense",
        ),
    ),
    cards=(
        CardSpec("Translate: «πήγα».", "I went", kind="reverse", due_in_days=0),
        CardSpec("What is the aorist of «βλέπω»?", "είδα", due_in_days=2),
        CardSpec("Translate: «Τι έκανες χθες;»", "What did you do yesterday?", due_in_days=4),
    ),
)

CONSTITUTIONAL_LAW = CourseSpec(
    title="Constitutional Law",
    description="Foundations of constitutional review — fictional cases only.",
    subject="Law",
    level="Year 1",
    course_type="generic",
    color="#7a5cff",
    exam_date="2027-01-18",
    goals=("Brief a case in under a page", "Separation of powers in three sentences"),
    tags=("cases", "essay"),
    chapters=("Separation of powers",),
    materials=(
        MaterialSpec(
            filename="01 — Separation of powers.md",
            title="01 — Separation of powers",
            markdown=(
                "# Separation of powers\n\n"
                "The doctrine splits state authority between the legislature "
                "(makes law), the executive (applies law) and the judiciary "
                "(reviews law).\n\n"
                "## Fictional case: *State v. Halloran* (2019)\n\n"
                "The fictional High Court held that delegated rule-making is "
                "valid only when the statute sets **intelligible principles** "
                "to guide the delegate.\n"
            ),
            summary="Doctrine outline plus the fictional Halloran principle.",
            topics=("separation of powers", "delegation"),
            key_terms=("legislature", "executive", "judiciary", "intelligible principles"),
            chapter="Separation of powers",
        ),
    ),
    notes=(
        NoteSpec(
            title="Case brief — State v. Halloran",
            body_md=(
                "# Case brief — *State v. Halloran*\n\n"
                "**Facts:** the fictional Minister for Transport set fares by "
                "decree under a one-line enabling act.\n\n"
                "**Holding:** the decree was ultra vires — no intelligible "
                "principles in the enabling act.\n"
            ),
            tags=("briefs",),
            chapter="Separation of powers",
        ),
    ),
    cards=(
        CardSpec("State the *Halloran* holding in one sentence.", "Delegated rule-making is valid only under intelligible principles set by the legislature.", due_in_days=1),
        CardSpec("Name the three branches.", "Legislature, executive, judiciary.", due_in_days=2),
        CardSpec("Ultra vires means …", "beyond one's legal power", kind="cloze", due_in_days=7),
    ),
)

LEGAL_WRITING = CourseSpec(
    title="Legal Writing",
    description="Structure, precision and editing — fictional assignments.",
    subject="Law",
    level="Year 1",
    course_type="language",
    color="#0ea5e9",
    exam_date="2027-03-09",
    goals=("Write a one-page brief", "Cut 20% without losing content"),
    tags=("writing", "editing"),
    chapters=("Brief structure",),
    materials=(
        MaterialSpec(
            filename="01 — Brief structure.md",
            title="01 — Brief structure",
            markdown=(
                "# Brief structure\n\n"
                "A one-page brief runs: **Question presented** (one sentence), "
                "**Short answer** (one paragraph), **Reasoning** (IRAC order), "
                "**Conclusion**.\n\n"
                "## Editing pass\n\n"
                "Delete throat-clearing openers (\"It is submitted that …\") and "
                "every adverb that does not change meaning.\n"
            ),
            summary="One-page brief skeleton and a ruthless editing pass.",
            topics=("briefs", "editing"),
            key_terms=("IRAC", "question presented", "short answer"),
            chapter="Brief structure",
        ),
    ),
    notes=(
        NoteSpec(
            title="Feedback from the mock brief",
            body_md=(
                "# Feedback from the mock brief\n\n"
                "- Question presented was two sentences — merge them.\n"
                "- Facts section: keep only facts the holding needs.\n"
            ),
            tags=("feedback",),
            chapter="Brief structure",
        ),
    ),
    cards=(
        CardSpec("What are the four parts of a one-page brief?", "Question presented, short answer, reasoning, conclusion.", due_in_days=3),
        CardSpec("IRAC expands to …", "Issue, Rule, Application, Conclusion", kind="cloze", due_in_days=5),
    ),
)

APPELLATE_ADVOCACY = CourseSpec(
    title="Appellate Advocacy",
    description="Moot court practice — fictional moot problem only.",
    subject="Law",
    level="Elective",
    course_type="generic",
    color="#2f9e6e",
    exam_date="2027-04-14",
    goals=("Deliver a 6-minute oral argument", "Handle a hostile bench"),
    tags=("moot", "oral"),
    chapters=("Oral argument",),
    materials=(
        MaterialSpec(
            filename="01 — Oral argument checklist.md",
            title="01 — Oral argument checklist",
            markdown=(
                "# Oral argument checklist\n\n"
                "- Roadmap the argument in the first 30 seconds.\n"
                "- Answer the bench's question *first*, then explain.\n"
                "- Concede what you can — credibility beats a lost point.\n"
            ),
            summary="Six habits for a clean appellate argument.",
            topics=("oral argument",),
            key_terms=("roadmap", "concession", "bench"),
            chapter="Oral argument",
        ),
    ),
    notes=(
        NoteSpec(
            title="Moot problem — opening lines",
            body_md=(
                "# Moot problem — opening lines\n\n"
                "\"May it please the court. The fictional Meridian Trust "
                "appeal turns on one question: notice.\""
            ),
            tags=("moot",),
            chapter="Oral argument",
        ),
    ),
    cards=(
        CardSpec("What do you do first when the bench asks a question?", "Answer the question, then explain.", due_in_days=0),
        CardSpec("How long is the opening roadmap?", "About 30 seconds.", kind="reverse", due_in_days=2),
    ),
)

STATISTICS = CourseSpec(
    title="Statistics for Biology",
    description="Inference, testing and regression for MSc biologists.",
    subject="Biology",
    level="MSc",
    course_type="math",
    color="#0ea5e9",
    exam_date="2026-11-24",
    goals=("Choose the right test", "Read a regression table"),
    tags=("inference", "regression"),
    chapters=("Hypothesis testing", "Regression"),
    materials=(
        MaterialSpec(
            filename="01 — Hypothesis testing.md",
            title="01 — Hypothesis testing",
            markdown=(
                "# Hypothesis testing\n\n"
                "We test $H_0$ against $H_1$. The p-value is the probability, "
                "*assuming $H_0$*, of data at least as extreme as observed.\n\n"
                "## Errors\n\n"
                "- Type I: rejecting a true $H_0$ (rate $\\alpha$).\n"
                "- Type II: keeping a false $H_0$ (rate $\\beta$).\n\n"
                "Never say \"accept $H_0$\" — say \"insufficient evidence to "
                "reject\".\n"
            ),
            summary="p-values, the two error types, and the phrasing that keeps marks.",
            topics=("p-value", "errors"),
            key_terms=("p-value", "Type I error", "Type II error", "H_0"),
            study_status="read",
            study_progress=1.0,
            chapter="Hypothesis testing",
        ),
        MaterialSpec(
            filename="02 — Regression basics.md",
            title="02 — Regression basics",
            markdown=(
                "# Regression basics\n\n"
                "The simple model $y = \\beta_0 + \\beta_1 x + \\varepsilon$ "
                "estimates the change in $y$ per unit change in $x$.\n\n"
                "## Reading the table\n\n"
                "- Coefficient: effect size (units of $y$).\n"
                "- Std. error: uncertainty.\n"
                "- p-value: evidence against $\\beta_i = 0$.\n"
            ),
            summary="Interpreting a simple linear regression output.",
            topics=("regression",),
            key_terms=("coefficient", "residual", "R-squared"),
            chapter="Regression",
        ),
    ),
    notes=(
        NoteSpec(
            title="Lab meeting notes",
            body_md=(
                "# Lab meeting notes\n\n"
                "The seedling dataset shows a significant mass–length "
                "relationship, but the residuals fan out — consider a log "
                "transform before trusting the slope.\n"
            ),
            tags=("lab",),
            chapter="Regression",
        ),
    ),
    cards=(
        CardSpec("Define a p-value.", "The probability, assuming H_0, of data at least as extreme as observed.", due_in_days=-2),
        CardSpec("A Type I error is …", "rejecting a true null hypothesis", kind="cloze", due_in_days=0),
        CardSpec("What does the slope estimate in $y = \\beta_0 + \\beta_1 x$?", "The change in y per unit change in x.", due_in_days=1),
        CardSpec("Why not say \"accept H_0\"?", "Failing to reject is not evidence that H_0 is true.", kind="reverse", due_in_days=4),
    ),
)

MOLECULAR_BIOLOGY = CourseSpec(
    title="Molecular Biology",
    description="The central dogma and gene regulation.",
    subject="Biology",
    level="MSc",
    course_type="science",
    color="#2f9e6e",
    exam_date="2026-12-15",
    goals=("Trace DNA → RNA → protein", "Explain operon logic"),
    tags=("genetics",),
    chapters=("Central dogma",),
    materials=(
        MaterialSpec(
            filename="01 — Central dogma.md",
            title="01 — Central dogma",
            markdown=(
                "# Central dogma\n\n"
                "Information flows DNA → RNA → protein. Transcription copies a "
                "gene into mRNA; translation reads mRNA in codons.\n\n"
                "## Exceptions worth knowing\n\n"
                "- Reverse transcription (RNA → DNA).\n"
                "- RNA replication in some viruses.\n"
            ),
            summary="The information-flow rule and its famous exceptions.",
            topics=("transcription", "translation"),
            key_terms=("codon", "mRNA", "reverse transcriptase"),
            chapter="Central dogma",
        ),
    ),
    notes=(
        NoteSpec(
            title="Revision list",
            body_md=(
                "# Revision list\n\n"
                "- Operon components: promoter, operator, repressor.\n"
                "- Codon table for the six serine codons.\n"
            ),
            tags=("revision",),
            chapter="Central dogma",
        ),
    ),
    cards=(
        CardSpec("State the central dogma.", "DNA → RNA → protein.", due_in_days=2),
        CardSpec("Which enzyme copies DNA into mRNA?", "RNA polymerase.", due_in_days=3),
        CardSpec("Reverse transcription copies …", "RNA into DNA", kind="cloze", due_in_days=6),
    ),
)

SPANISH_B2 = CourseSpec(
    title="Spanish B2",
    description="Subjunctive, conversation and idiom for the B2 exam.",
    subject="Languages",
    level="B2",
    course_type="language",
    color="#d97706",
    exam_date="2027-06-08",
    goals=("Subjunctive without hesitation", "Ten idioms in active use"),
    tags=("conversation", "grammar"),
    chapters=("Subjunctive",),
    materials=(
        MaterialSpec(
            filename="01 — Subjunctive triggers.md",
            title="01 — Subjunctive triggers",
            markdown=(
                "# Subjunctive triggers\n\n"
                "Use the subjunctive after **wish, doubt, emotion and "
                "recommendation**: «Quiero que *vengas*».\n\n"
                "## Fixed triggers\n\n"
                "- «para que» + subjunctive\n"
                "- «ojalá» + subjunctive\n"
                "- «a menos que» + subjunctive\n"
            ),
            summary="The trigger categories and three fixed phrases.",
            topics=("subjunctive",),
            key_terms=("subjuntivo", "ojalá", "para que"),
            study_status="reading",
            study_progress=0.6,
            chapter="Subjunctive",
        ),
    ),
    notes=(
        NoteSpec(
            title="Conversation vocabulary",
            body_md=(
                "# Conversation vocabulary\n\n"
                "- «me da la impresión de que …» (I get the impression that …)\n"
                "- «en todo caso …» (in any case …)\n"
            ),
            tags=("speaking",),
            chapter="Subjunctive",
        ),
    ),
    cards=(
        CardSpec("Translate: «Ojalá llueva mañana.»", "I hope it rains tomorrow.", kind="reverse", due_in_days=1),
        CardSpec("«para que» triggers which mood?", "the subjunctive", kind="cloze", due_in_days=3),
        CardSpec("Complete: «Quiero que ___ (venir).»", "vengas", due_in_days=5),
    ),
)

DEMO_USERS: tuple[UserSpec, ...] = (
    UserSpec(
        key="ava",
        full_name="Ava Lindqvist",
        email="ava.lindqvist@demo.study.local",
        is_admin=True,
        profiles=(
            ProfileSpec(
                key="cs",
                name="Computer Science BSc",
                color="#4f7cff",
                courses=(LINEAR_ALGEBRA, DATABASES),
            ),
            ProfileSpec(
                key="greek",
                name="Evening Greek class",
                color="#e2725b",
                courses=(GREEK_A2,),
            ),
        ),
    ),
    UserSpec(
        key="marco",
        full_name="Marco Ferreira",
        email="marco.ferreira@demo.study.local",
        profiles=(
            ProfileSpec(
                key="law",
                name="Law school",
                color="#7a5cff",
                courses=(CONSTITUTIONAL_LAW, LEGAL_WRITING),
            ),
            ProfileSpec(
                key="moot",
                name="Moot court",
                color="#2f9e6e",
                courses=(APPELLATE_ADVOCACY,),
            ),
        ),
    ),
    UserSpec(
        key="nora",
        full_name="Nora Okafor",
        email="nora.okafor@demo.study.local",
        profiles=(
            ProfileSpec(
                key="bio",
                name="Biology MSc",
                color="#0ea5e9",
                courses=(STATISTICS, MOLECULAR_BIOLOGY),
            ),
            ProfileSpec(
                key="spanish",
                name="Spanish B2",
                color="#d97706",
                courses=(SPANISH_B2,),
            ),
        ),
    ),
)


# --------------------------------------------------------------------------
# Guard rails — refuse anything that is not a demo target/instance.
# --------------------------------------------------------------------------


@dataclass
class Target:
    url: str
    demo_dir: Path | None
    blobs_dir: Path


def ensure_demo_target(url: str, demo_dir: Path | None, blobs_dir: Path) -> Target:
    parsed = make_url(url)
    backend = parsed.get_backend_name()
    if backend == "sqlite":
        if demo_dir is None:
            raise Refusal(
                "SQLite target without an explicit --demo-dir — refusing to seed "
                "anything but an isolated demo data dir (identity-auth §13)."
            )
        demo_root = demo_dir.resolve()
        database = Path(parsed.database or "")
        db_path = (database if database.is_absolute() else Path.cwd() / database).resolve()
        if demo_root != db_path and demo_root not in db_path.parents:
            raise Refusal(
                f"SQLite database {db_path} is not inside the demo data dir "
                f"{demo_root} — refusing (identity-auth §13)."
            )
        return Target(url=url, demo_dir=demo_root, blobs_dir=blobs_dir)
    if backend == "postgresql":
        name = parsed.database or ""
        if not name.endswith("_demo"):
            raise Refusal(
                f"target database {name!r} is not a demo database — expected a "
                "name ending '_demo' (deployment.md: neuro_study_demo); refusing "
                "(identity-auth §13)."
            )
        return Target(url=url, demo_dir=demo_dir, blobs_dir=blobs_dir)
    raise Refusal(f"unsupported database backend {backend!r} — refusing.")


def ensure_demo_instance(session: Session, *, init_demo: bool) -> str:
    row = session.get(InstanceSetting, "demo_mode")
    if row is not None and row.value == "true":
        return "demo_mode=true (instance_settings)"
    if not init_demo:
        raise Refusal(
            "instance_settings.demo_mode is not 'true' — refusing to seed a "
            "non-demo instance (identity-auth §13). Use --init-demo to "
            "initialize an EMPTY demo database."
        )
    if not _instance_is_empty(session):
        raise Refusal(
            "--init-demo requires an EMPTY demo database (found existing "
            "instance data) — refusing to re-flag an existing instance as demo "
            "(identity-auth §13)."
        )
    session.add(InstanceSetting(key="demo_mode", value="true"))
    session.commit()
    return "demo_mode=true (--init-demo)"


def _instance_is_empty(session: Session) -> bool:
    if session.get(InstanceSetting, "demo_mode") is not None:
        return False
    if session.get(InstanceSetting, "auth_mode") is not None:
        return False
    for model in (User, Profile, Course):
        if session.scalars(select(model).limit(1)).first() is not None:
            return False
    return True


# --------------------------------------------------------------------------
# Reset — remove previously seeded demo rows (and the demo principal's),
# never anything else.
# --------------------------------------------------------------------------


def purge_seeded(session: Session) -> dict[str, int]:
    user_ids = [demo_id("user", spec.key) for spec in DEMO_USERS] + [DEMO_PRINCIPAL_ID]
    user_ids = [
        row
        for row in session.scalars(select(User.id).where(User.id.in_(user_ids))).all()
    ]
    empty = {"users": 0}
    if not user_ids:
        return empty
    profile_ids = list(
        session.scalars(select(Profile.id).where(Profile.user_id.in_(user_ids))).all()
    )
    counts = {"users": len(user_ids)}
    if not profile_ids:
        session.execute(delete(User).where(User.id.in_(user_ids)))
        session.commit()
        return counts
    course_ids = list(
        session.scalars(select(Course.id).where(Course.profile_id.in_(profile_ids))).all()
    )
    note_ids = list(
        session.scalars(select(Note.id).where(Note.profile_id.in_(profile_ids))).all()
    )
    material_ids = list(
        session.scalars(
            select(Material.id).where(Material.profile_id.in_(profile_ids))
        ).all()
    )
    exercise_ids = list(
        session.scalars(
            select(Exercise.id).where(Exercise.profile_id.in_(profile_ids))
        ).all()
    )
    node_ids = list(
        session.scalars(select(TreeNode.id).where(TreeNode.course_id.in_(course_ids))).all()
    ) if course_ids else []
    extraction_ids = list(
        session.scalars(
            select(Extraction.id).where(Extraction.material_id.in_(material_ids))
        ).all()
    ) if material_ids else []

    def run(statement: Any) -> int:
        result = session.execute(statement)
        return int(result.rowcount or 0)

    run(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
    if extraction_ids:
        run(delete(Chunk).where(Chunk.extraction_id.in_(extraction_ids)))
        run(delete(Extraction).where(Extraction.id.in_(extraction_ids)))
    if material_ids:
        run(delete(MaterialIndexCard).where(MaterialIndexCard.material_id.in_(material_ids)))
        run(delete(MaterialStudyState).where(MaterialStudyState.material_id.in_(material_ids)))
        run(delete(MaterialLink).where(MaterialLink.material_id.in_(material_ids)))
        counts["materials"] = run(delete(Material).where(Material.id.in_(material_ids)))
    if note_ids:
        run(delete(NoteVersion).where(NoteVersion.note_id.in_(note_ids)))
        counts["notes"] = run(delete(Note).where(Note.id.in_(note_ids)))
    if exercise_ids:
        run(delete(FsrsState).where(FsrsState.card_id.in_(exercise_ids)))
        run(delete(ExerciseStep).where(ExerciseStep.exercise_id.in_(exercise_ids)))
        counts["flashcards"] = run(delete(Exercise).where(Exercise.id.in_(exercise_ids)))
    if node_ids:
        run(delete(MaterialLink).where(MaterialLink.node_id.in_(node_ids)))
        for node_id in sorted(node_ids, reverse=True):
            run(delete(TreeNode).where(TreeNode.id == node_id))
        counts["nodes"] = len(node_ids)
    if course_ids:
        counts["courses"] = run(delete(Course).where(Course.id.in_(course_ids)))
    counts["profiles"] = run(delete(Profile).where(Profile.id.in_(profile_ids)))
    run(delete(User).where(User.id.in_(user_ids)))
    session.commit()
    return counts


# --------------------------------------------------------------------------
# Seeding — get-or-create everything, so re-running changes no counts.
# --------------------------------------------------------------------------


@dataclass
class SeedCounts:
    totals: dict[str, int] = field(default_factory=dict)
    created: dict[str, int] = field(default_factory=dict)

    def add(self, entity: str, is_new: bool) -> None:
        self.totals[entity] = self.totals.get(entity, 0) + 1
        if is_new:
            self.created[entity] = self.created.get(entity, 0) + 1


def _ensure_user(
    session: Session, spec: UserSpec, password_hash: str
) -> tuple[User, bool]:
    """User rows are created here (not via the auth kit's store) so the
    whole workspace lands in one transaction — with the §6 Default
    profile provisioned in the same flush."""
    row = session.get(User, demo_id("user", spec.key))
    if row is not None:
        return row, False
    email = spec.email.lower().strip()
    existing = session.scalar(select(User).where(User.email == email))
    if existing is not None:
        return existing, False
    row = User(
        id=demo_id("user", spec.key),
        email=email,
        password_hash=password_hash,
        full_name=spec.full_name,
        is_admin=spec.is_admin,
    )
    session.add(row)
    session.flush()
    session.add(
        Profile(
            id=demo_id("profile", f"{row.id}:default"),
            user_id=row.id,
            name="Default",
            is_default=True,
        )
    )
    session.flush()
    return row, True


def _ensure_profile(session: Session, user: User, spec: ProfileSpec) -> tuple[Profile, bool]:
    profile_id = demo_id("profile", f"{user.id}:{spec.key}")
    row = session.get(Profile, profile_id)
    if row is not None:
        return row, False
    existing = session.scalar(
        select(Profile).where(Profile.user_id == user.id, Profile.name == spec.name)
    )
    if existing is not None:
        return existing, False
    row = Profile(
        id=profile_id,
        user_id=user.id,
        name=spec.name,
        is_default=False,
        color=spec.color,
    )
    session.add(row)
    session.flush()
    return row, True


def _course_type_id(session: Session, key: str) -> int | None:
    row = session.scalar(select(CourseType).where(CourseType.key == key))
    return row.id if row is not None else None


def _ensure_course(
    session: Session, profile: Profile, spec: CourseSpec
) -> tuple[Course, bool]:
    row = session.scalar(
        select(Course).where(Course.profile_id == profile.id, Course.title == spec.title)
    )
    if row is not None:
        return row, False
    row = Course(
        profile_id=profile.id,
        title=spec.title,
        description=spec.description,
        subject=spec.subject,
        level=spec.level,
        goals=list(spec.goals),
        tags=list(spec.tags),
        color=spec.color,
        exam_date=date.fromisoformat(spec.exam_date) if spec.exam_date else None,
        course_type_id=_course_type_id(session, spec.course_type),
    )
    session.add(row)
    session.flush()
    return row, True


def _ensure_chapter(
    session: Session, tree: TreeService, course: Course, root_id: int, title: str
) -> tuple[TreeNode, bool]:
    row = session.scalar(
        select(TreeNode).where(
            TreeNode.course_id == course.id,
            TreeNode.parent_id == root_id,
            TreeNode.title == title,
        )
    )
    if row is not None:
        return row, False
    return tree.create_node(course.id, root_id, title), True


def _ensure_material(
    session: Session,
    blobs: BlobStore,
    profile: Profile,
    course: Course,
    spec: MaterialSpec,
) -> tuple[Material, bool]:
    row = session.scalar(
        select(Material).where(
            Material.profile_id == profile.id,
            Material.course_id == course.id,
            Material.title == spec.title,
        )
    )
    if row is not None:
        return row, False
    data = spec.markdown.encode("utf-8")
    stored = blobs.put(data, mime="text/markdown", session=session)
    row = Material(
        profile_id=profile.id,
        course_id=course.id,
        kind=detect_kind(spec.filename),
        title=spec.title,
        blob_sha=stored.sha256,
        filename=spec.filename,
        mime="text/markdown",
        status="processing",
        content_hash=stored.sha256,
    )
    session.add(row)
    session.flush()
    _store_extraction(session, row, extractor="native", markdown=spec.markdown, pages=None)
    sync_material_fts(session, row, spec.markdown)
    row.status = "ready"
    card = session.scalar(
        select(MaterialIndexCard).where(MaterialIndexCard.material_id == row.id)
    )
    if card is None:
        card = MaterialIndexCard(material_id=row.id)
        session.add(card)
    card.summary = spec.summary
    card.topics = list(spec.topics)
    card.key_terms = list(spec.key_terms)
    card.reading_minutes = spec.reading_minutes
    card.difficulty = spec.difficulty
    session.add(
        MaterialStudyState(
            material_id=row.id,
            profile_id=profile.id,
            status=spec.study_status,
            progress=spec.study_progress,
            last_opened_at=utcnow() - timedelta(days=2) if spec.study_progress else None,
        )
    )
    session.flush()
    return row, True


def _ensure_note(
    session: Session, profile: Profile, course: Course, spec: NoteSpec
) -> tuple[Note, bool]:
    row = session.scalar(
        select(Note).where(
            Note.profile_id == profile.id,
            Note.course_id == course.id,
            Note.title == spec.title,
        )
    )
    if row is not None:
        return row, False
    row = Note(
        profile_id=profile.id,
        course_id=course.id,
        owner_type="standalone",
        title=spec.title,
        body=md_to_blocks(spec.body_md),
        tags=normalize_tags(list(spec.tags)),
    )
    row.search_text = note_search_text(row)
    session.add(row)
    session.flush()
    return row, True


def _ensure_card(
    session: Session, profile: Profile, course: Course, spec: CardSpec
) -> tuple[Exercise, bool]:
    title = front_title([{"type": "text", "md": spec.front}])
    row = session.scalar(
        select(Exercise).where(Exercise.course_id == course.id, Exercise.title == title)
    )
    if row is not None:
        return row, False
    row = create_card_exercise(
        session,
        profile_id=profile.id,
        course_id=course.id,
        node_id=None,
        kind=spec.kind,
        front=[{"type": "text", "md": spec.front}],
        back=[{"type": "text", "md": spec.back}],
        source="demo",
    )
    session.add(
        FsrsState(
            card_id=row.id,
            state="review",
            stability=2.5,
            difficulty=5.0,
            reps=1,
            lapses=0,
            due_at=utcnow() + timedelta(days=spec.due_in_days),
            last_review_at=utcnow() - timedelta(days=1) if spec.due_in_days <= 3 else None,
        )
    )
    session.flush()
    return row, True


def seed_workspace(session: Session, blobs: BlobStore) -> SeedCounts:
    counts = SeedCounts()
    seed_course_types(session)
    session.commit()
    password_hash = _demo_password_hash()
    for user_spec in DEMO_USERS:
        user, user_new = _ensure_user(session, user_spec, password_hash)
        counts.add("users", user_new)
        for profile_spec in user_spec.profiles:
            profile, profile_new = _ensure_profile(session, user, profile_spec)
            counts.add("profiles", profile_new)
            for course_spec in profile_spec.courses:
                course, course_new = _ensure_course(session, profile, course_spec)
                counts.add("courses", course_new)
                tree = TreeService(session)
                root = tree.ensure_root(course.id)
                chapters: dict[str, int] = {}
                for chapter_title in course_spec.chapters:
                    node, node_new = _ensure_chapter(
                        session, tree, course, root.id, chapter_title
                    )
                    counts.add("nodes", node_new)
                    chapters[chapter_title] = node.id
                for material_spec in course_spec.materials:
                    material, material_new = _ensure_material(
                        session, blobs, profile, course, material_spec
                    )
                    counts.add("materials", material_new)
                    chapter_id = chapters.get(material_spec.chapter)
                    if material_new and chapter_id is not None:
                        session.add(
                            MaterialLink(
                                course_id=course.id,
                                node_id=chapter_id,
                                material_id=material.id,
                                rationale="demo seed",
                                auto_assigned=False,
                            )
                        )
                for note_spec in course_spec.notes:
                    note, note_new = _ensure_note(session, profile, course, note_spec)
                    counts.add("notes", note_new)
                    chapter_id = chapters.get(note_spec.chapter)
                    if note_new and chapter_id is not None:
                        note.node_id = chapter_id
                for card_spec in course_spec.cards:
                    _, card_new = _ensure_card(session, profile, course, card_spec)
                    counts.add("flashcards", card_new)
    session.commit()
    return counts


def scope_totals(session: Session) -> dict[str, int]:
    """Row counts for the seeded scope — stable across idempotent runs."""
    user_ids = list(
        session.scalars(
            select(User.id).where(User.id.in_(demo_id("user", spec.key) for spec in DEMO_USERS))
        ).all()
    )
    profile_ids = (
        list(session.scalars(select(Profile.id).where(Profile.user_id.in_(user_ids))).all())
        if user_ids
        else []
    )
    course_ids = (
        list(session.scalars(select(Course.id).where(Course.profile_id.in_(profile_ids))).all())
        if profile_ids
        else []
    )

    def count(statement: Any) -> int:
        return int(session.scalar(statement) or 0)

    return {
        "users": count(select(func.count()).select_from(User).where(User.id.in_(user_ids))),
        "profiles": count(
            select(func.count()).select_from(Profile).where(Profile.id.in_(profile_ids))
        ),
        "courses": count(
            select(func.count()).select_from(Course).where(Course.id.in_(course_ids))
        ),
        "nodes": count(
            select(func.count())
            .select_from(TreeNode)
            .where(TreeNode.course_id.in_(course_ids), TreeNode.is_root.is_(False))
        ),
        "materials": count(
            select(func.count())
            .select_from(Material)
            .where(Material.profile_id.in_(profile_ids))
        ),
        "notes": count(
            select(func.count()).select_from(Note).where(Note.profile_id.in_(profile_ids))
        ),
        "flashcards": count(
            select(func.count())
            .select_from(Exercise)
            .where(Exercise.profile_id.in_(profile_ids))
        ),
    }


_PASSWORD_CACHE: list[str] = []


def _demo_password_hash() -> str:
    if not _PASSWORD_CACHE:
        from nx_auth.passwords import hash_password

        _PASSWORD_CACHE.append(hash_password(DEMO_PASSWORD))
    return _PASSWORD_CACHE[0]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="seed-demo.py",
        description="Seed synthetic demo data into a demo instance (identity-auth §13).",
    )
    parser.add_argument(
        "--database-url",
        help="target URL (else SA_DATABASE_URL / SA_DB_* settings; URL wins)",
    )
    parser.add_argument(
        "--demo-dir",
        type=Path,
        help="the isolated demo data dir (required for SQLite targets)",
    )
    parser.add_argument(
        "--init-demo",
        action="store_true",
        help="initialize demo_mode=true on an EMPTY demo database",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="remove previously seeded demo rows (and the demo principal's), then reseed",
    )
    return parser.parse_args(argv)


def resolve_target(args: argparse.Namespace) -> Target:
    explicit = args.database_url or os.environ.get("SA_DATABASE_URL") or None
    demo_dir: Path | None = args.demo_dir
    if explicit is None and demo_dir is not None:
        url = f"sqlite:///{demo_dir / 'study.sqlite3'}"
    elif explicit is not None:
        url = explicit
    else:
        from app.core.config import Settings

        url = Settings().db_url
    if demo_dir is not None:
        blobs_dir = demo_dir
        blobs_dir.mkdir(parents=True, exist_ok=True)
    else:
        raw_data_dir = os.environ.get("SA_DATA_DIR") or ""
        if raw_data_dir:
            blobs_dir = Path(raw_data_dir)
        else:
            from app.core.config import Settings

            blobs_dir = Settings().data_dir
    return ensure_demo_target(url, demo_dir, blobs_dir)


def run_migrations(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    engine = make_engine(url)
    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def has_schema(engine: Any) -> bool:
    return "instance_settings" in inspect(engine).get_table_names()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        target = resolve_target(args)
    except Refusal as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return EXIT_REFUSED
    engine = make_engine(target.url)
    try:
        if not has_schema(engine) and not args.init_demo:
            print(
                "REFUSED: the target has no Study Assistant schema and --init-demo "
                "was not given — refusing to initialize anything but an explicitly "
                "declared empty demo database (identity-auth §13).",
                file=sys.stderr,
            )
            return EXIT_REFUSED
        run_migrations(target.url)
        factory = make_session_factory(engine)
        with factory() as session:
            try:
                mode = ensure_demo_instance(session, init_demo=args.init_demo)
            except Refusal as refusal:
                print(f"REFUSED: {refusal}", file=sys.stderr)
                return EXIT_REFUSED
            purged: dict[str, int] = {}
            if args.reset:
                purged = purge_seeded(session)
            counts = seed_workspace(session, BlobStore(target.blobs_dir))
            counts.totals.update(scope_totals(session))
    except Refusal as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return EXIT_REFUSED
    finally:
        engine.dispose()

    print("Demo seed complete — synthetic data only (identity-auth §13).")
    print(f"  instance: {mode}")
    print(f"  database: {target.url.split('@')[-1]}")
    if target.demo_dir is not None:
        print(f"  demo dir: {target.demo_dir}")
    if args.reset:
        removed = ", ".join(f"{key}={value}" for key, value in sorted(purged.items())) or "nothing"
        print(f"  reset: removed {removed}")
    for entity in ("users", "profiles", "courses", "nodes", "materials", "notes", "flashcards"):
        total = counts.totals.get(entity, 0)
        created = counts.created.get(entity, 0)
        print(f"  {entity}: {total} ({created} created this run)")
    print(f"  demo users share the password: {DEMO_PASSWORD}")
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refusal as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        sys.exit(EXIT_REFUSED)
    except Exception as error:  # noqa: BLE001
        print(f"seed-demo.py failed: {error}", file=sys.stderr)
        sys.exit(EXIT_ERROR)
