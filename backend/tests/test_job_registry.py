"""Job dispatch completeness (plan 82 C, ADR-204).

Every `JobType` member has a registered handler and every registered handler
is a `JobType` member — a typo'd key silently drops jobs, a missing member is
a job the API can enqueue but never run.
"""

from typing import Any, cast

from fastapi.testclient import TestClient

from app.core.vocab import JobType


def test_every_job_type_has_a_handler_and_vice_versa(client: TestClient) -> None:
    runner = cast(Any, client.app).state.jobs
    registered = runner.handler_types
    declared = {job_type.value for job_type in JobType}
    assert registered == declared
    for job_type in JobType:
        assert runner.has_handler(job_type.value)
