# JRU Library-Assist

A responsive web app for the PewPewPew Library-Assist RAG chatbot experiment. Includes library chat, cited FAQ passages, searchable knowledge base, and interactive original experiment results.

## Run locally

Install Node.js 22 or newer, then open a terminal in this folder:

```sh
npm start
```

Visit **http://127.0.0.1:3000**. There are no package dependencies to install. The server binds only to your own computer.

Alternatively double-click `start-local.cmd` on Windows (requires Node.js on PATH, or the bundled Codex runtime).

### Answer modes

1. **FAQ retrieval (default):** BM25 keyword retrieval over 293 deduplicated FAQ records, with aliases for common library terms. Returns the best source excerpt, cited by worksheet and row. No provider key, external AI call, model download, or database required.
2. **Groq grounded answers:** Copy `.env.example` to `.env` and set `GROQ_API_KEY` locally. Restart the server. Retrieved FAQ passages are sent to Groq to generate a cited answer. `GROQ_MODEL` defaults to `openai/gpt-oss-20b`, matching the original experiment. This remains BM25 retrieval, not the original semantic retrieval. Provider failures fall back to the source excerpt with an explicit notice.
3. **Original semantic RAG (local bridge):** Run the original `Chatbot/app.py` from the ZIP in its own Python environment, following that project's dependencies and configuration. Set `ORIGINAL_RAG_URL=http://127.0.0.1:5000` in this app’s `.env`. Restart this Node server. It forwards chat turns to the existing Flask app, preserving its MiniLM, ChromaDB, Groq, and conversation pipeline. The bridge is intentionally disabled on Vercel; a deployed server cannot reach your computer's loopback address. The website never executes notebook cells itself.
4. **Browser FAQ mode:** If served as static files without the API (for example on GitHub Pages), the same keyword retrieval runs in the browser. Groq and the original bridge require a backend.

Conversation history is stored in this browser’s local storage. New conversation clears the current saved conversation. Download conversation exports the visible conversation with its sources. The app does not maintain a cloud chat database. In Groq mode, the question, recent conversation, and retrieved evidence are sent to Groq for response generation.

## GitHub and Vercel

The deployment project root is this folder, which contains `package.json`, `vercel.json`, `public/`, `api/`, and `lib/`.

1. Push this folder’s contents to the `JRU-Library-Assist` GitHub repository.
2. Import that repository into Vercel. Framework preset: **Other**. Output directory: **public**. Leave the build command empty. No dependency installation is needed.
3. Deploy. The two `api/*.mjs` endpoints run as Node.js Vercel Functions; frontend assets are served from `public/`.
4. Optional: add `GROQ_API_KEY` in the Vercel project's Environment Variables, and redeploy. Never add a key to browser JavaScript, GitHub, or a `PUBLIC_` environment variable.

The app works immediately in source-excerpt FAQ mode without credentials. A Groq key is required only for generated answers. There is no public API-key entry field.

## Data and experiment provenance

Data is derived from `PewPewPew_Final_Experiment_Results (2).zip` supplied by the user. The import uses `all_source_faq_records.csv`, `run_manifest.json`, and recorded result CSVs from its reproducibility package. It reproduces the notebook’s normalization and deduplication by question, option, and answer: **542 source records → 293 unique FAQs across 14 worksheets**. Duplicate worksheet references are retained. Account-number-like source text is redacted during import. Personal statements, member responsibility documents, the original `.env`, and the Chroma database are not published.

The experiment page shows original recorded MiniLM/Chroma results. It does not claim those metrics were produced by this web app. Config B remains the recorded default; Config C has the highest recorded Recall@3 (88.9%). All @3 values, including E, are copied from the original `chunking_comparison.csv`.

To regenerate bundled public data from the extracted reproducibility results:

```sh
python scripts/import-data.py /path/to/results
```

FAQ content includes historical and pandemic-era rules. The app is an academic prototype, not an official JRU service, and cannot check live availability or updated policy. Important details should be confirmed with library staff.

## Verification

```sh
npm test
```

Tests check imported record counts and references, grounded retrieval for common questions, unsupported-question refusal, input validation, and mode labelling.

## Structure

```text
public/             Static interface, browser retrieval, imported FAQ/result data
api/                Vercel chat and status endpoints
lib/chat.mjs        Shared retrieval/generation and local bridge
server.mjs          Dependency-free local server
scripts/            Reproducible data import
tests/              Source integrity and chat behavior checks
```
