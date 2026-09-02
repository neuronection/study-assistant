import json

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


def _chat_payload(request_body: dict) -> str:
    messages = request_body.get("messages", [])
    for message in messages:
        role = str(message.get("role"))
        content = str(message.get("content", ""))
        if role == "tool" or (role == "system" and "Verified tool results" in content):
            print("MOCK: tool-result round", flush=True)
            return "The tool says the result is 4. So the answer to your question is 4."
    for message in messages:
        if str(message.get("role")) == "system" and "quiz designer" in str(
            message.get("content", "")
        ):
            print("MOCK: quizgen round", flush=True)
            return QUIZ_JSON
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
