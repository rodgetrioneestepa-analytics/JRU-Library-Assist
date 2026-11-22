# Corrected conversational RAG

This implementation follows the user's `PewPewPew_Final_RAG_Chatbot_Conversational_Fixed.ipynb`, replacing the previous PDF/FAISS implementation.

## Pipeline

- Reads both workbook layouts across all 14 sheets with openpyxl, retaining option/answer relationships and continuation rows.
- Deduplicates by normalized question + option + answer and retains all source references internally.
- Flags conflicting or review-sensitive entries; masks account-number-like values before evidence is used.
- Uses sentence-transformers/all-MiniLM-L6-v2, normalized embeddings, and persistent ChromaDB cosine collections.
- Default notebook configuration B: 800-character FAQ-aware recursive chunks, 100 overlap, top 3, provisional minimum similarity 0.35.
- Follows the notebook's natural-language Groq prompt with openai/gpt-oss-20b, temperature 0, and 700 completion tokens.
- Rewrites follow-ups using at most six recent messages and 450 completion tokens. Missing choices, missing content, blank lines, unusable short responses, and exceptions preserve the original question. There is no unsafe indexing into an empty response.
- Retrieves fresh evidence after rewriting. History resolves references only; it is never factual evidence.
- Handles greetings and thanks without a provider call; refuses unsupported live/private requests.
- Keeps conversation history in the caller's browser/request, without shared server-global conversation state.

## Run

Use Python 3.12 in the project directory:

```sh
python -m venv .venv
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install -r rag_backend/requirements.txt
.venv\Scripts\python -m rag_backend
```

On Linux/macOS use .venv/bin/python. Open http://127.0.0.1:5000. The Python service serves the website and API together. First startup downloads MiniLM weights to .model-cache/ and prepares .chroma-cache/. Both are ignored by Git.

Set GROQ_API_KEY privately in .env for generation and follow-up rewriting. Without a key, the semantic backend can return a matched FAQ answer directly, without an LLM. The Node fallback uses lexical retrieval and can use Groq when a key is supplied. Neither mode is presented as the other in the technical documentation; the user interface contains no implementation or dataset panels.

The original workbook stays outside the public folder. Set RAG_WORKBOOK to an optional local workbook path, or use the prepared server_data/faqs.json. Do not put a key in source control.

## Hosted connection

Dockerfile.rag packages this service for a Python/container host. Use RAG_BACKEND_TOKEN for server-to-server access; configure the same token and an HTTPS RAG_BACKEND_URL on Vercel. The normal local Python mode uses no token. Status returns only ready/service, and chat returns only answer/refused.

## Verification

Run `python -m unittest discover -s tests -p test_conversation.py -v`. Fake provider responses exercise the corrected empty-response behavior without consuming quota. API tests inject an engine and do not establish that a real model has run. See the task's verification report for real semantic checks.
