# JRU Library-Assist

A JRU-inspired blue and gold web app using the supplied mascot and the new PewPewPew RAG Experiment Notebook. The active source is the notebook’s verified four-page Basic Information FAQ PDF.

## Local website

Run `npm start` with Node.js 22, then open http://127.0.0.1:3000. No Node dependencies are required. This mode uses explicitly labelled BM25 retrieval over the same 17 PDF chunks. Set GROQ_API_KEY privately in .env for schema- and quote-validated generation.

## Python semantic RAG

See [rag_backend/README.md](rag_backend/README.md) for setup. Run `python -m rag_backend` in the project environment, then open http://127.0.0.1:5000. This serves the website and API with MiniLM + FAISS retrieval. Groq and FLAN-T5 generation are optional. Windows shortcut: start-rag.cmd.

Windows Application Control blocked FAISS’s native DLL on this computer. PDF extraction, its fingerprint, all twelve chunk counts, evidence validation, and the API contract were tested. A real semantic-model run remains unverified here; no security policy was changed.

## GitHub and Vercel

[Repository](https://github.com/rodgetrioneestepa-analytics/JRU-Library-Assist) · [Website](https://jru-library-assist.vercel.app)

Vercel serves public/ and the Node endpoints in api/. The heavy Python backend is separate. To connect it, deploy Dockerfile.rag on a Python/container host and configure RAG_BACKEND_URL (HTTPS) and the same private RAG_BACKEND_TOKEN on both services. A deployed service cannot reach this computer’s localhost. See the backend README.

## Verification

Run `npm test` and `python -m unittest discover -s tests -p test_rag.py -v`. Python API tests use an injected engine, without a model download.

## Provenance

The PDF fingerprint matches the new notebook. Its nine evaluation questions, twelve configurations, prompt and schema were imported as literal data without executing notebook cells. Chart values come from the notebook’s saved output and are labelled provisional, not rerun. Earlier workbook data remains archived in public/data/faqs.json and experiments.json.

Conversations are browser-local. Groq mode sends questions and retrieved passages to Groq. This is an academic prototype, not an official JRU service; source policies are not verified current.
