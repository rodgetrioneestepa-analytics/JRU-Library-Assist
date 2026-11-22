# Conversational Python backend

The authoritative runtime is `core.py` (source/index/retrieval), `generation.py` (notebook prompts and Groq calls), `service.py` (chat-turn behavior), and `app.py` (HTTP API).

For local development with Python 3.12:

```sh
python -m venv .venv
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install -r rag_backend/requirements.txt
.venv\Scripts\python -m rag_backend
```

Set `GROQ_API_KEY` in ignored `.env`. Local startup can read the prepared source plus ignored `server_data/private-overrides.json`, or load `RAG_WORKBOOK` directly. Production uses the corresponding private environment variable. A missing key or override returns HTTP 503; there is no answer substitution. The Flask development server binds to 127.0.0.1:5000. The production Waitress entry point honors PORT and binds to 0.0.0.0.

Data parsing preserves wide-format and topic-format sheets, duplicate provenance, review reasons, and original answer text for embeddings. Redaction occurs before external generation and browser responses. Index identity changes with records, chunks, configuration, model weights, or dependency versions. The default B settings are enforced by the HTTP runtime.

`GET /api/status` initializes the real engine and returns readiness, pipeline identity, and a non-sensitive index fingerprint. It does not validate provider credentials through a paid model call. `POST /api/chat` returns answer, refusal flag, rewritten query, numbered source excerpts, ranked retrieval metadata, and timing. Sources must match the current retrieved passages. Both APIs use no-store; raw workbook and prepared files are outside public/ and return 404. An optional RAG_BACKEND_TOKEN requires bearer authorization for a separately hosted backend.

Conversation history is client-provided, limited to six valid user/assistant messages, and never stored in server-global chat state. Every factual question retrieves fresh evidence. Follow-up failures use the original question, as in the notebook. Unsupported live/private requests and below-threshold results return the exact notebook refusal. The first generation request matches the notebook. Every non-refusal draft gets one extra evidence-verification request using the same passages, model, temperature and 700-token budget. Structured output associates each concise claim with an explicit current passage number validated before rendering. Identical claims are merged. The reviewer uses low reasoning effort within the same 700-token budget; strict output may fall back to JSON mode with identical server validation. It must refuse when any part of a question lacks current evidence; it must not infer a new permission from a restriction. This is an explicit website safeguard beyond the notebook, not an exact generation-path match. It can increase latency and quota usage. Malformed or uncited responses still fail closed. Groq request limits return HTTP 429 and Retry-After with a clear retry message.

