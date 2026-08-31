import pytest

from app.core.vocab import (
    AttemptMode,
    JobStatus,
    JobType,
    MaterialKind,
    WsTopic,
)


def test_parse_accepts_values_and_rejects_unknown() -> None:
    assert JobStatus.parse("queued") is JobStatus.QUEUED
    assert MaterialKind.parse("pdf") is MaterialKind.PDF
    with pytest.raises(ValueError, match="allowed"):
        JobStatus.parse("archived")


def test_strenum_compares_equal_to_its_value() -> None:
    assert JobStatus.QUEUED == "queued"
    assert JobStatus.QUEUED.value == "queued"
    assert str(JobStatus.QUEUED) == "queued"


def test_job_status_active_pair() -> None:
    assert JobStatus.active() == (JobStatus.QUEUED, JobStatus.RUNNING)


def test_ws_topic_factories() -> None:
    assert WsTopic.jobs(3) == "jobs:3"
    assert WsTopic.chat(9) == "chat:9"
    assert WsTopic.source(1) == "source:1"
    assert WsTopic.note(2) == "note:2"
    assert WsTopic.material(4) == "material:4"


def test_vocabularies_are_disjoint_where_required() -> None:
    job_values = {s.value for s in JobStatus}
    type_values = {t.value for t in JobType}
    assert not job_values & type_values
    mode_values = {m.value for m in AttemptMode}
    kind_values = {k.value for k in MaterialKind}
    assert not mode_values & kind_values
