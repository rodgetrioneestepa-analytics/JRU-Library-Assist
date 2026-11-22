# JRU Library-Assist

A JRU navy-and-gold library chat app using the corrected conversational notebook's Python pipeline. The existing mascot, chat interface, responsive sidebar, New Chat button, and export remain. Numbered citations open only the passages retrieved for that answer; the app has no dataset inventory or bulk download page.

## Runtime

Production uses `Dockerfile.vercel` and Vercel's Container Runtime. Flask serves `public/` and the API together through Waitress. Every factual question uses normalized `sentence-transformers/all-MiniLM-L6-v2` embeddings, ChromaDB cosine retrieval, RecursiveCharacterTextSplitter 800/100, top 3, and minimum similarity 0.35. Groq `openai/gpt-oss-20b` generates at temperature 0 and 700 completion tokens. Follow-up rewriting uses 450 tokens and the last six messages. Prompts and the refusal are extracted from the corrected notebook.

There is no keyword or stored-answer fallback. Missing configuration, invalid source integrity, or unavailable dependencies return an unavailable response. The optional Node server is a development proxy and requires `RAG_BACKEND_URL`; it cannot answer questions on its own.

## Production configuration

Set these as Vercel Production Secrets before deploying:

- `GROQ_API_KEY`: your Groq key.
- `RAG_PRIVATE_RECORD_OVERRIDES`: contents of the ignored local `server_data/private-overrides.json` generated from the supplied workbook. Never commit this file or print its contents in build logs.

The Git-published `server_data/faqs.json` contains all 293 deduplicated records from 542 rows across 14 worksheets, with sensitive payment text redacted. The private override restores the original record only for notebook-equivalent embeddings; evidence is redacted before Groq and browser responses. Source and override fingerprints are checked before indexing. A missing override fails readiness instead of silently changing the vectors.

MiniLM weights are downloaded during the remote image build and baked into the deployment. The canonical source is the image's prepared records plus the Vercel secret, not temporary storage. Chroma is a reconstructible cache in `/tmp`; each cold instance rebuilds from the durable source if necessary. Collection identity includes source content, chunk settings, weights, and library versions. Rebuilding may increase cold-start latency. No source editing or user uploads are supported.

## Local use

Use Python 3.12, install CPU Torch and `rag_backend/requirements.txt`, set `GROQ_API_KEY` privately in `.env`, and run `python -m rag_backend`. Visit http://127.0.0.1:5000. The ignored private override file is used locally, or set `RAG_WORKBOOK` to the original workbook. See [backend instructions](rag_backend/README.md).

Regenerate prepared records and reviewed notebook constants without running notebook setup cells:

```sh
python scripts/prepare-chatbot.py /path/to/corrected.ipynb /path/to/CONSOLIDATED_FAQs.xlsx
```

## Verification

```sh
npm test
python -m unittest discover -s tests -p test_conversation.py -v
python scripts/evaluate-parity.py --notebook /path/to/corrected.ipynb --workbook /path/to/CONSOLIDATED_FAQs.xlsx
python scripts/evaluate-parity.py --url https://jru-library-assist.vercel.app --output .rag-results/deployed-parity.json
```

The local evaluator uses reviewed functions from the actual notebook and independently built Chroma collections. It checks record/chunk equality, all 12 retrieval rankings/scores, and exact Groq payloads using deterministic completion stubs. It does not claim live generation was tested. Remote mode calls real production Groq and compares rankings, valid passage citations, refusal rules, and conversational requests. Reports are ignored locally; publish only reviewed, redacted summaries.

Conversations are browser-local and supplied per request, never shared server history. New Chat clears the active history. Groq receives the question, limited history, and current redacted evidence. API keys never enter browser code. Older Git history can contain earlier public exports; removing current website files does not rewrite that history.
