from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text:latest"


def request_json(base_url: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
    return json.loads(body.decode("utf-8"))


def request_bytes(base_url: str, path: str, payload: dict[str, Any]) -> tuple[int, bytes, str]:
    url = base_url.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Accept": "audio/mpeg, application/octet-stream, application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "")


def model_names(tags_payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for model in tags_payload.get("models", []):
        name = model.get("name") or model.get("model")
        if isinstance(name, str) and name:
            names.append(name)
    return names


def embedding_vector(payload: dict[str, Any]) -> list[Any] | None:
    if isinstance(payload.get("embedding"), list):
        return payload["embedding"]
    embeddings = payload.get("embeddings")
    if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
        return embeddings[0]
    return None


def check_embedding(base_url: str, embedding_model: str, names: list[str]) -> None:
    if embedding_model not in names:
        raise RuntimeError(
            f'Embedding model "{embedding_model}" is not registered in Ollama. '
            f"Available models: {', '.join(names) if names else '(none)'}"
        )

    text = "OpenNotebookLM Ollama embedding smoke test"
    try:
        payload = request_json(base_url, "/api/embed", {"model": embedding_model, "input": text})
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        payload = request_json(base_url, "/api/embeddings", {"model": embedding_model, "prompt": text})

    vector = embedding_vector(payload)
    if not vector:
        raise RuntimeError(f'Embedding model "{embedding_model}" returned no embedding vector.')
    if not all(isinstance(value, (int, float)) for value in vector[:8]):
        raise RuntimeError(f'Embedding model "{embedding_model}" returned a malformed embedding vector.')

    print(f"OK: Ollama embedding model {embedding_model} returned a {len(vector)}-dimension vector.")


def check_qwen_tts(base_url: str, names: list[str], strict: bool) -> None:
    configured = os.environ.get("OLLAMA_QWEN_TTS_MODEL", "").strip()
    candidates = [name for name in names if "qwen" in name.lower() and "tts" in name.lower()]
    model = configured or (candidates[0] if candidates else "")

    if configured and configured not in names:
        message = (
            f'WARN: OLLAMA_QWEN_TTS_MODEL is "{configured}", but that model is not registered in Ollama. '
            f"Available models: {', '.join(names) if names else '(none)'}"
        )
        if strict:
            raise RuntimeError(message.replace("WARN: ", ""))
        print(message)
        return

    if not model:
        message = (
            "WARN: No Qwen TTS model is registered in Ollama. "
            "The current local Ollama model list cannot prove Qwen TTS support."
        )
        if strict:
            raise RuntimeError(message.replace("WARN: ", ""))
        print(message)
        return

    status, body, content_type = request_bytes(
        base_url,
        "/v1/audio/speech",
        {"model": model, "input": "OpenNotebookLM TTS smoke test", "voice": "default"},
    )
    if status == 200 and body and "audio" in content_type.lower():
        print(f"OK: Ollama returned audio bytes from Qwen TTS model {model}.")
        return

    preview = body[:160].decode("utf-8", errors="replace").replace("\r", " ").replace("\n", " ")
    message = (
        f'WARN: Qwen TTS model candidate "{model}" is registered, but Ollama did not return audio '
        f"from /v1/audio/speech. HTTP {status}; response: {preview}"
    )
    if strict:
        raise RuntimeError(message.replace("WARN: ", ""))
    print(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local Ollama readiness for OpenNotebookLM.")
    parser.add_argument("--strict-tts", action="store_true", help="Fail if Qwen TTS cannot return audio through Ollama.")
    args = parser.parse_args()

    base_url = os.environ.get("OLLAMA_API_BASE") or os.environ.get("OLLAMA_BASE_URL") or DEFAULT_BASE_URL
    embedding_model = os.environ.get("OLLAMA_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)

    try:
        tags = request_json(base_url, "/api/tags")
        names = model_names(tags)
        if not names:
            raise RuntimeError("Ollama API is reachable, but no models are registered.")
        print(f"OK: Ollama API is reachable at {base_url}.")
        check_embedding(base_url, embedding_model, names)
        check_qwen_tts(base_url, names, args.strict_tts)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
