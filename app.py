"""Multi-LLM answer comparison, select which is more relevant to your question.

Each browser session owns a conversation object with separate message histories per
provider. Providers are called concurrently so a slow model does not delay others.

Author: Nitin Katakdound
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import sys
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

# When packaged, keep credentials beside the executable rather than embedding
# them into it. During normal development this remains the project `.env`.
RUNTIME_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
load_dotenv(RUNTIME_DIR / ".env")
app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=32 * 1024, JSON_SORT_KEYS=False)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

PROVIDERS = {
    # Provider metadata is sent to the UI; API keys always remain server-side.
    "groq": {"label": "Groq", "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")},
    "qwen": {"label": "Qwen", "model": os.getenv("QWEN_MODEL", "qwen/qwen3.8-27b")},
    "llama": {"label": "OpenRouter Free", "model": os.getenv("OPENROUTER_MODEL", "openrouter/free")},
}

# Deliberately in-memory: histories disappear when the server restarts, and are
# never shared between browser sessions. Replace with Redis/database for production.
conversations: dict[str, dict] = {}


def new_conversation() -> tuple[str, dict]:
    """Create an isolated, in-memory history for one browser conversation."""
    conversation = {
        "histories": {key: [] for key in PROVIDERS},
        "active_provider": None,
    }
    conversation_id = str(uuid.uuid4())
    conversations[conversation_id] = conversation
    return conversation_id, conversation


def demo_reply(provider: str, prompt: str) -> str:
    """Keep the interface usable when a provider key has not been configured."""
    return (
        f"**Demo mode — {PROVIDERS[provider]['label']} is not configured.**\n\n"
        f"I received: {prompt}\n\n"
        "Add this provider's API key to `.env`, restart the server, and this card will use the live model."
    )


def ask_groq(history: list[dict]) -> str:
    """Send one conversation history to Groq's OpenAI-compatible endpoint."""
    if not os.getenv("GROQ_API_KEY", "").strip():
        return demo_reply("groq", history[-1]["content"])
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={"model": PROVIDERS["groq"]["model"], "messages": history},
        timeout=90,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def ask_qwen(history: list[dict]) -> str:
    """Run Qwen remotely through Groq using the shared Groq credential."""
    if not os.getenv("GROQ_API_KEY", "").strip():
        return demo_reply("qwen", history[-1]["content"])
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={"model": PROVIDERS["qwen"]["model"], "messages": history},
        timeout=90,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def ask_llama(history: list[dict]) -> str:
    """Run a free, online model through OpenRouter's compatible chat API."""
    if not os.getenv("OPENROUTER_API_KEY", "").strip():
        return demo_reply("llama", history[-1]["content"])
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json={"model": PROVIDERS["llama"]["model"], "messages": history},
        timeout=90,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


ASKERS = {"groq": ask_groq, "qwen": ask_qwen, "llama": ask_llama}


def answer(provider: str, history: list[dict]) -> dict:
    """Return a UI-safe answer/error payload without exposing provider secrets."""
    try:
        text = ASKERS[provider](history)
        return {"provider": provider, "answer": text}
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else None
        app.logger.warning("%s provider returned HTTP %s", provider, status)
        if status == 401:
            message = "Provider rejected the API key. Verify the key and its project restrictions."
        elif status == 429:
            message = "Provider quota or rate limit reached. Add billing/credits or wait before trying again."
        else:
            message = "Provider request was rejected. Check the model, API key, and server logs."
        return {"provider": provider, "error": message}
    except requests.RequestException as error:
        app.logger.warning("%s provider request failed: %s", provider, type(error).__name__)
        return {"provider": provider, "error": "Provider request failed. Check the API key, model, and server logs."}
    except (KeyError, IndexError, TypeError) as error:
        return {"provider": provider, "error": f"Unexpected provider response: {error}"}


@app.get("/")
def index():
    return render_template("index.html", providers=PROVIDERS)


@app.post("/api/chat")
def chat():
    # A selected provider becomes the only continuation target; otherwise compare all.
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return jsonify(error="Please enter a question."), 400

    conversation_id = payload.get("conversation_id")
    conversation = conversations.get(conversation_id)
    if conversation is None:
        conversation_id, conversation = new_conversation()

    requested = payload.get("providers")
    active = conversation["active_provider"]
    providers = [active] if active else (requested or list(PROVIDERS))
    providers = [name for name in providers if name in PROVIDERS]
    if not providers:
        return jsonify(error="Choose at least one supported model."), 400

    for provider in providers:
        conversation["histories"][provider].append({"role": "user", "content": prompt})
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)) as pool:
        results = list(pool.map(lambda name: answer(name, conversation["histories"][name]), providers))
    for result in results:
        if "answer" in result:
            conversation["histories"][result["provider"]].append({"role": "assistant", "content": result["answer"]})

    return jsonify(conversation_id=conversation_id, active_provider=active, results=results,
                   timestamp=datetime.now(timezone.utc).isoformat())


@app.post("/api/continue")
def continue_with():
    payload = request.get_json(silent=True) or {}
    conversation = conversations.get(payload.get("conversation_id"))
    provider = payload.get("provider")
    if conversation is None or provider not in PROVIDERS:
        return jsonify(error="Conversation or provider was not found."), 404
    conversation["active_provider"] = provider
    return jsonify(active_provider=provider, label=PROVIDERS[provider]["label"])


@app.post("/api/reset")
def reset():
    conversation_id, _ = new_conversation()
    return jsonify(conversation_id=conversation_id)


if __name__ == "__main__":
    # Debug mode exposes an interactive debugger and must remain off for live use.
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    # The installed program is a local web application.  Opening the browser
    # here makes its Start Menu/Desktop shortcuts behave like a normal app.
    if getattr(sys, "frozen", False):
        threading.Timer(0.8, webbrowser.open_new_tab, args=(f"http://{host}:{port}",)).start()
    app.run(
        host=host,
        debug=os.getenv("FLASK_DEBUG") == "1",
        port=port,
    )
