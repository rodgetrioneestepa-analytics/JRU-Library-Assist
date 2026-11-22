# JRU Library-Assist

A conversational JRU library assistant with the transparent mascot and blue-and-gold theme. The website is chat-only: it does not display dataset filenames, inventories, source panels, or research dashboards.

The current implementation follows `PewPewPew_Final_RAG_Chatbot_Conversational_Fixed.ipynb` and the supplied `CONSOLIDATED FAQs for VLA.xlsx`.

## Local Python RAG

See [rag_backend/README.md](rag_backend/README.md). Run `python -m rag_backend` in the project environment and visit http://127.0.0.1:5000, or use start-rag.cmd.

The Python backend uses MiniLM embeddings, persistent ChromaDB cosine retrieval, FAQ-aware recursive splitting (800 characters / 100 overlap / top 3), and optional conversational Groq generation. The corrected follow-up rewrite safely falls back to the original message for empty choices, blank text, invalid short rewrites, or provider errors. History is limited to six messages per request, never global across visitors, and supplies reference context rather than factual evidence.

## Local Node / Vercel

Run `npm start` with Node.js 22 and open http://127.0.0.1:3000. This dependency-free server uses lexical FAQ retrieval unless RAG_BACKEND_URL connects it to the Python service. Add GROQ_API_KEY privately in .env or Vercel for follow-up rewriting and conversational generation.

Vercel serves public/ and api/. To use semantic retrieval online, host Dockerfile.rag on a Python/container service, set RAG_BACKEND_URL to its HTTPS origin, and set the same private RAG_BACKEND_TOKEN on both services. A deployed server cannot reach this computer's localhost. The browser receives only answers and basic availability status, without internal source metadata.

## Data preparation

The original workbook is not in public/. Parsed FAQ records live in server_data/faqs.json. To regenerate them and the notebook prompts without executing notebook cells:

```sh
python scripts/prepare-chatbot.py /path/to/corrected.ipynb /path/to/CONSOLIDATED_FAQs.xlsx
```

The prior PDF exports and research JSON files are removed from the public website assets. This does not erase earlier Git commit history.

## Checks

```sh
npm test
python -m unittest discover -s tests -p test_conversation.py -v
```

These cover workbook layout parsing, deduplication, empty rewrite handling, bounded visitor history, prompts, validation, API response shape, and the absence of dataset views in the website. Model integration checks are reported separately from injected-engine unit tests.

Conversations are browser-local. Groq-enabled mode sends the current question, limited history, and current retrieved evidence to Groq. No API key is placed in browser JavaScript.
