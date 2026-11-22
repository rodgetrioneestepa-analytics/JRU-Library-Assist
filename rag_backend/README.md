# Notebook-based Python RAG

This is a modular rewrite of `PewPewPew_RAG_Experiment_Notebook (1) (1).ipynb`, not a notebook executor.

## Source and preserved behavior

- Source: the four-page `CONSOLIDATED FAQs for VLA - Basic information.pdf`.
- Verified SHA-256: `e9daef1fe5201b08b8cda91a54ec4009d3046ab3d877973e4da0f56398ca54a6`.
- Whitespace-normalized pypdf extraction, preserving physical one-based PDF page numbers.
- Page-local character chunks: 1,000 characters, 200 overlap, 17 baseline chunks.
- `sentence-transformers/all-MiniLM-L6-v2`, normalized float32 embeddings.
- FAISS `IndexFlatIP`: cosine ranking over normalized vectors, six candidates, three deduplicated passages.
- Groq `openai/gpt-oss-20b`, temperature 0, 2,048 completion tokens, low reasoning effort, strict JSON schema.
- Notebook statuses: answered, insufficient, conflict. Quotes must occur verbatim in the cited source, allowing whitespace differences. These checks establish source presence; they do not prove that a claim follows from its quote.
- Each query is independent, matching the notebook. History is not used as factual evidence or to guess missing referents.
- Optional FLAN-T5 Base baseline: 512 input tokens, 16 reserved tokens, 32 output tokens, deterministic four-beam generation. It is labelled as baseline output, without the Groq quote-validation guarantee.

The notebook's Colab file dialogs, package-install cells, interactive input loops, pickle exports, and automatic notebook execution were replaced by explicit APIs, configuration, JSON, and commands. The original notebook is unchanged.

## Run locally

Use Python 3.12 in an environment that permits the native PyTorch and FAISS libraries:

```sh
python -m venv .venv
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install -r rag_backend/requirements.txt
.venv\Scripts\python -m rag_backend
```

On macOS/Linux, use `.venv/bin/python` instead of `.venv\Scripts\python`.

Open **http://127.0.0.1:5000**. This Python service serves both the website and API; Node is not needed for this local mode. First startup downloads MiniLM weights to the ignored `.model-cache/` folder.

Without a generation key, real semantic retrieval returns explicitly labelled PDF excerpts. To enable generated answers, copy `.env.example` to `.env`, set `GROQ_API_KEY` privately, and restart. Set `RAG_GENERATOR=flan-t5` to opt into the larger local baseline-model download instead.

Windows shortcut: `start-rag.cmd`.

### Verification limitation on the current computer

The isolated dependencies installed successfully, but Windows Application Control blocked FAISS's native `_swigfaiss` DLL. No security policy was changed. Therefore a fresh semantic-model run, model download, and CPU/GPU benchmark were **not verified on this machine**. The five Python tests pass, including the real PDF extraction/fingerprint, every reference quote, all twelve notebook chunk counts, citation validation, and the Flask API using an injected test engine. Those tests do not substitute for a real FAISS/model test.

## Hosted website and semantic backend

The existing Vercel deployment serves the branded website and Node endpoints. Its default is an explicitly labelled **BM25 fallback over this same PDF**, with optional quote-validated Groq generation. It does not pretend that BM25 is FAISS. The heavy PyTorch/FAISS backend is kept outside the Vercel frontend build.

To connect a separately hosted Python service:

1. Deploy this folder's `Dockerfile.rag` on a Python/container host.
2. Set the same private `RAG_BACKEND_TOKEN` on the Python host and Vercel.
3. Set Vercel's `RAG_BACKEND_URL` to that service's HTTPS origin and redeploy.
4. The Node API proxies requests server to server. Neither that token nor `GROQ_API_KEY` is sent to the browser. The mode badge reflects the backend's actual mode.

For local Node proxying, set `RAG_BACKEND_URL=http://127.0.0.1:5000`. A deployed Vercel server cannot reach this computer's localhost.

## Evaluation

The question key and twelve configurations are parsed with AST as literal data. They are never included in generation messages. Confirm all nine evidence keys against the exact PDF before evaluation:

```sh
.venv\Scripts\python -m unittest discover -s tests -p test_rag.py -v
.venv\Scripts\python -m rag_backend.evaluate
```

The evaluation command performs real MiniLM/FAISS runs and writes actual measurements to `.rag-results/retrieval-evaluation.json`. Recall@3 is evidence-unit recall, Precision@3 counts relevant retrieved chunks divided by three, and MRR@3 is reciprocal rank of the first relevant chunk. Scores use full reference-passage containment and remain provisional pending human review. No GPU or generation benchmarks are fabricated.

The website's twelve result rows are imported from the supplied notebook's saved dataframe output, labelled **recorded, provisional, not rerun**. The earlier workbook experiment remains in `public/data/experiments.json` as an archive; it is not shown as the new notebook's results.

## Files

- `core.py`: PDF extraction, configuration, chunking, MiniLM and FAISS retrieval, payload validation.
- `generation.py`: structured Groq generation and optional FLAN baseline.
- `app.py`: local/static website, status and chat API, optional server token.
- `evaluate.py`: real twelve-configuration/nine-question retrieval evaluation.
- `notebook_spec.json`: safely imported constants, evaluation key, prompt, schema and notebook fingerprint.
