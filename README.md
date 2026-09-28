# Parallel Chat

Author: Nitin Katakdound

A comparison UI that sends every question to Groq GPT-OSS, Qwen, and a free online OpenRouter model concurrently. Each provider has its own history; choosing **Continue with this model** keeps only that provider's conversation going.

## Run it

1. Install Python 3.10+ and create a virtual environment.
2. Run `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and add one or more API keys.
4. Run `python app.py`, then open `http://127.0.0.1:5000`.

## Windows installer

Run `powershell -ExecutionPolicy Bypass -File .\build-installer.ps1`. It builds
`installer\ParallelChat-Setup.exe`. Running that installer adds a **Parallel
Chat** Start Menu shortcut (and, if selected, a desktop shortcut). Launching a
shortcut starts the local application and opens it automatically in the default
browser. The installed `.env` is created once and retained during upgrades, so
add API keys there after installation if you want live provider responses.

If a key is absent, that card deliberately shows a demo reply so the interface can be explored without credentials. Conversations are held in server memory and reset on restart; use a database or Redis plus authentication before deploying publicly.

## Configure live providers

Create `.env` from `.env.example` and paste only keys issued by the respective
provider dashboards. `.env` is ignored by Git and must never be committed:

```env
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key
```

The OpenRouter card uses its free online model router (`openrouter/free`); the Groq and Qwen cards use `GROQ_API_KEY`. Unconfigured cards stay in demo mode.

## Deploy

Use a managed host's encrypted environment-variable settings for the provider API
keys; do not upload `.env`. Start the production server with:

```bash
waitress-serve --host=0.0.0.0 --port=$PORT app:app
```

Set `PORT` only if your platform does not provide it. Before exposing this app
publicly, add authentication and a shared session store (Redis/database): it
currently keeps conversations in one process's memory and any visitor can use
your provider quota.

## Project layout

- `app.py` — Flask API, concurrent provider calls, per-provider histories
- `templates/index.html` and `static/` — responsive comparison UI
