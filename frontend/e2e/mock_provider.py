import json
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()

QUIZ_JSON = json.dumps(
    {
        "questions": [
            {
                "type": "single",
                "stem_md": "What is 2 + 2?",
                "options_md": ["3", "4", "5", "22"],
                "answer": {"index": 1},
                "explanation_md": "Two plus two equals four.",
                "concepts": ["arithmetic"],
                "skill": "procedural",
                "bloom": "remember",
                "difficulty": 1,
                "expected_time_sec": 30,
            }
        ]
    }
)


def _demo_user_text(messages: list) -> str:
    for message in reversed(messages):
        if str(message.get("role")) == "user":
            return str(message.get("content", "")).lower()
    return ""


# Demo scripts (family demo-tour standard): deterministic, useful canned
# answers keyed by prompt intent — the same idea as Health Assistant's
# embedded automated responses for specific input. The real chat pipeline
# parses the answer text, so tool lines, grounded citations, chart blocks
# and proposal cards render exactly as they would for a live model.
DEMO_INTENTS = ("flashcard", "vector space", "recall trend", "study plan")


def _demo_study_tools() -> str:
    """Round 1: ground the answer in the student's own materials."""
    return (
        "Let me ground this in your course material first.\n\n"
        "FIND vector space basis and dimension\n"
    )


def _demo_study_answer() -> str:
    """Round 2 (tool results in): the rich study answer."""
    return (
        "Here is a focused pass on **vector spaces**.\n\n"
        "A *basis* of $\\mathbb{R}^n$ is $n$ linearly independent vectors: "
        "every vector in the space is a unique linear combination of them [1]. "
        "The **dimension** is just how many vectors any basis needs — which is "
        "why every basis of the same space has the same size [2].\n\n"
        "```chart\n"
        '{"data": [{"x": [1, 2, 3, 4], "y": [62, 58, 66, 71], '
        '"type": "scatter", "mode": "lines+markers", "name": "Recall %"}], '
        '"layout": {"title": "Recall trend across reviews", "height": 260}}\n'
        "```\n\n"
        "Your recall is trending back up — the last two reviews landed above "
        "65%, so the spaced schedule is working.\n\n"
        "```proposal\n"
        '{"action": "generate_flashcards", "material_id": null, '
        '"note_id": null, "count": 8}\n'
        "```\n"
    )


def _chat_payload(request_body: dict) -> str:
    messages = request_body.get("messages", [])
    demo_intent = any(k in _demo_user_text(messages) for k in DEMO_INTENTS)
    for message in messages:
        role = str(message.get("role"))
        content = str(message.get("content", ""))
        if role == "tool" or (role == "system" and "Verified tool results" in content):
            print("MOCK: tool-result round", flush=True)
            if demo_intent:
                return _demo_study_answer()
            return "The tool says the result is 4. So the answer to your question is 4."
    for message in messages:
        if str(message.get("role")) == "system" and "quiz designer" in str(
            message.get("content", "")
        ):
            print("MOCK: quizgen round", flush=True)
            return QUIZ_JSON
    if demo_intent:
        print("MOCK: demo study round", flush=True)
        return _demo_study_tools()
    print("MOCK: default round", flush=True)
    return (
        "Let me compute that for you.\n\nCALC 2+2\n\nOne moment while I check the math."
    )


@app.get("/v1/models")
def models() -> dict:
    return {
        "object": "list",
        "data": [{"id": "mock-text", "object": "model"}, {"id": "mock-embed", "object": "model"}],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    content = _chat_payload(body)
    model = body.get("model", "mock-text")
    if body.get("stream"):
        def sse():
            first = {"id": "1", "object": "chat.completion.chunk", "model": model,
                     "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
            yield f"data: {json.dumps(first)}\n\n"
            for token in content.split(" "):
                time.sleep(0.06)
                chunk = {"id": "1", "object": "chat.completion.chunk", "model": model,
                         "choices": [{"index": 0, "delta": {"content": f"{token} "}, "finish_reason": None}]}
                yield f"data: {json.dumps(chunk)}\n\n"
            final = {"id": "1", "object": "chat.completion.chunk", "model": model,
                     "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}}
            yield f"data: {json.dumps(final)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream")
    return JSONResponse(
        {
            "id": "1",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }
    )


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    body = await request.json()
    inputs = body.get("input", [])
    if isinstance(inputs, str):
        inputs = [inputs]
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": index, "embedding": [0.1, 0.2, 0.3, 0.4]}
            for index in range(len(inputs))
        ],
        "model": body.get("model", "mock-embed"),
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }
