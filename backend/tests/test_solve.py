from typing import Any, cast

from fastapi.testclient import TestClient


def solve(client: TestClient, text: str, kind: str = "typed") -> dict[str, Any]:
    response = client.post("/api/v1/solve", json={"input_text": text, "input_kind": kind})
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_solve_quadratic_has_verified_steps(client: TestClient) -> None:
    with client:
        entry = solve(client, "x^2 - 5x + 6 = 0")

        assert entry["intent"] == "solve"
        assert entry["verified"] is True
        assert entry["note_id"] is None
        result = entry["result"]
        assert "2" in result["answer_latex"] and "3" in result["answer_latex"]
        assert result["steps"]
        assert all(step["verified"] for step in result["steps"])
        assert {step["check"] for step in result["steps"]} >= {"equivalence", "substitution"}

        history = client.get("/api/v1/solve/history").json()
        assert [row["id"] for row in history] == [entry["id"]]
        detail = client.get(f"/api/v1/solve/{entry['id']}")
        assert detail.status_code == 200
        assert detail.json()["result"]["verified"] is True


def test_derivative_and_integral_pass_their_checks(client: TestClient) -> None:
    with client:
        derivative = solve(client, "differentiate x^2 + 3x")
        assert derivative["intent"] == "differentiate"
        assert derivative["result"]["answer_latex"] == "2 x + 3"
        assert derivative["result"]["steps"][0]["check"] == "derivative"

        integral = solve(client, "integrate x*cos(x)")
        assert integral["intent"] == "integrate"
        assert integral["verified"] is True
        assert "sin" in integral["result"]["answer_latex"]
        assert integral["result"]["steps"][0]["check"] == "antiderivative"
        assert integral["result"]["assumptions"] == ["C is an arbitrary constant."]


def test_unsupported_and_unparsed_inputs_are_honest(client: TestClient) -> None:
    with client:
        unsupported = solve(client, "limit x^2 as x->2")
        assert unsupported["intent"] == "limit"
        assert unsupported["verified"] is False
        assert unsupported["result"]["answer_latex"] is None
        assert "does not verify limits" in unsupported["result"]["message"]

        definite = solve(client, r"\int_{0}^{1} x^2 dx")
        assert definite["verified"] is False
        assert "Definite integrals" in definite["result"]["message"]

        bad = solve(client, "not math at all")
        assert bad["verified"] is False
        assert bad["result"]["answer_latex"] is None
        assert bad["result"]["message"]

        invalid = client.post("/api/v1/solve", json={"input_text": "", "input_kind": "typed"})
        assert invalid.status_code == 422


def test_variants_are_generated_and_checked_server_side(client: TestClient) -> None:
    with client:
        entry = solve(client, "x^2 - 5x + 6 = 0")
        variants = client.post(f"/api/v1/solve/{entry['id']}/variants")
        assert variants.status_code == 200, variants.text
        rows = variants.json()
        assert len(rows) == 3
        assert all("answer_display" not in row for row in rows)
        assert all(row["prompt"].startswith("Solve:") for row in rows)

        correct = client.post(
            f"/api/v1/solve/{entry['id']}/variants/check",
            json={"index": rows[0]["index"], "response": "4, 5"},
        )
        assert correct.status_code == 200, correct.text
        assert correct.json()["correct"] is True
        assert correct.json()["expected"] == "x = 4, x = 5"

        wrong = client.post(
            f"/api/v1/solve/{entry['id']}/variants/check",
            json={"index": rows[0]["index"], "response": "1, 2"},
        )
        assert wrong.json()["correct"] is False


def test_solve_can_be_saved_as_a_scratch_note_and_deleted_independently(
    client: TestClient,
) -> None:
    with client:
        entry = solve(client, "integrate x*cos(x)")
        saved = client.post(f"/api/v1/solve/{entry['id']}/note")
        assert saved.status_code == 201, saved.text
        note_id = saved.json()["note_id"]

        note = client.get(f"/api/v1/notes/{note_id}")
        assert note.status_code == 200, note.text
        body = note.json()
        assert body["title"].startswith("Solved:")
        assert "Verified steps" in str(body)

        linked = client.get(f"/api/v1/solve/{entry['id']}").json()
        assert linked["note_id"] == note_id

        assert client.delete(f"/api/v1/solve/{entry['id']}").status_code == 204
        assert client.get(f"/api/v1/solve/{entry['id']}").status_code == 404
        assert client.get(f"/api/v1/notes/{note_id}").status_code == 200


def test_unverified_solve_cannot_be_saved_as_a_note(client: TestClient) -> None:
    with client:
        entry = solve(client, "limit x^2 as x->2")
        response = client.post(f"/api/v1/solve/{entry['id']}/note")
        assert response.status_code == 422
