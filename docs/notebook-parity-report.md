# Notebook parity verification

Status: local comparison passed. Python container deployed, but source initialization is blocked by malformed private configuration; live Groq evaluation is pending.

## Original differences

Production ran BM25 over whole records and returned stored answers because neither a Python backend URL nor Groq key was configured. It did not execute the notebook MiniLM/Chroma path. Browser rendering removed citations and replaced the refusal. The full workbook was already present, but payment redaction occurred before embeddings and review flags differed.

## Implementation

- core.py: exact workbook parsers, deduplication, provenance/review strings, raw-text embeddings, private override integrity, configuration/model/content-versioned Chroma cache.
- generation.py and notebook_spec.json: reviewed notebook answer/rewrite prompts, exact model and token budgets, guarded empty completions.
- service.py and app.py: six-message per-request history, fresh retrieval, threshold/unsupported refusal, real citation metadata, fail-closed API errors. No shared visitor history.
- lib/chat.mjs: proxy only; keyword retrieval removed.
- public/app.mjs and chat-only.css: preserve answer text and make numbered citations open actual passages; existing interface retained.
- Dockerfile.vercel, serve.py, build-model.py and vercel.json: Python container, model packaged at build, source outside public assets. Legacy Node API handlers removed.
- prepare-chatbot.py and evaluate-parity.py: reproducible source preparation and independent notebook comparison.

## Configuration

All 14 named worksheets processed, preserving source order: 542 parsed rows, 293 unique records, 296 chunks. Workbook SHA256: `87c3407927e546fa50682b6c92052d34ee5f33221f189d18bd274b6646cb1adb`.

Normalized all-MiniLM-L6-v2 embeddings on CPU; Chroma cosine; RecursiveCharacterTextSplitter 800 characters/100 overlap/top 3; minimum similarity 0.35. Groq openai/gpt-oss-20b, temperature 0, completion limit 700; follow-up limit 450; history six messages. These are the notebook active B settings.

Canonical source consists of the sanitized prepared file plus a private environment override for one payment record, checked against fingerprints before indexing. The model is baked into the image. Temporary Chroma storage is a reconstructible cache, never the only source. Account information is redacted before Groq and browser responses.

## Local results

11 Python checks and 6 Node checks passed. The independent comparator ran reviewed functions from the supplied notebook, not a reimplementation of its retrieval oracle. Records and chunks were equal. It built two independent Chroma collections using a shared actual encoder; all ranks/IDs/scores matched within 1e-6. Exact Groq request payloads were compared with deterministic completion stubs; these are not live LLM quality tests.

| Case | Notebook evaluation question | Rank/score/prompt parity | Gold source coverage |
|---|---|---|---|
| E1 | What does OPAC stand for? | PASS | 100% |
| E2 | What are the Main Library's Saturday hours according to the FAQ? | PASS | 100% |
| E3 | How many Learning Commons reservations can students make per day? | PASS | 100% |
| A1 | What are the online and email ways to renew a library book? | PASS | 50% |
| A2 | How does a student pay a library fine at the cashier? | PASS | 100% |
| A3 | What should a student do if they left their ID at home? | PASS | 100% |
| D1 | What should a student with an overdue book and unpaid fines do about renewal and payment? | PASS | 100% |
| D2 | Can a student take a borrowed library laptop into class and install extra workstation software themselves? | PASS | 50% |
| D3 | How long may a student borrow a library laptop and reserve a Learning Commons room? | PASS | 50% |
| U1 | What is the actual Wi-Fi password for JRU LIB3? | PASS | Not applicable (refusal) |
| U2 | How many seats are empty in the Main Library right now? | PASS | Not applicable (refusal) |
| U3 | Which librarian is physically on duty at this exact moment? | PASS | Not applicable (refusal) |

Duplicate records retain their first canonical worksheet reference and all aliases. Gold coverage is measured by deduplicated record IDs, so a valid citation such as FAQs!8 can also cover its OPAC!3 duplicate.

The notebook itself retrieves only half the gold entries for A1, D2, and D3. Matching retrieval does not mean every multi-part question has complete evidence. No custom ranking bonus was added to mask these notebook limitations.

Follow-up, topic-switch, and new-session rewrite prompt comparisons also passed. Empty/error rewrite responses preserve the original query. Missing key/override and unsupported/low-similarity branches fail closed. Payment evidence is redacted before the provider call.

## Production verification

GROQ_API_KEY and RAG_PRIVATE_RECORD_OVERRIDES are present as production variables. Their values were not retrieved or displayed. Production deployment dpl_FsKdeghs2eft1dUZkVPduFdBspaA built the actual model image and is assigned to the public URL. However, /api/status returned HTTP 503 and logs report JSONDecodeError during source initialization: the private override is malformed JSON. The user was asked to replace it with the complete ignored local file contents. Provider acceptance, live generated answers, deployed ranking, and citations cannot be verified until the secret is corrected and a fresh production deployment receives it. Local prompt equivalence is not proof of working production generation.

The first preview inherited the previous static project preset and finished without building a model. The project framework was explicitly changed to Container, build overrides cleared, and large-function support enabled. The successful image builds installed CPU Torch 2.15.0, sentence-transformers 5.7.0, transformers 4.57.6, Chroma 1.5.9 and splitter 1.1.3, matching the local comparison. The browser confirmed the preview interface renders and fails closed without Preview secrets. Flask checks returned 404 for raw/prepared/private source URLs. Desktop/mobile production conversation checks remain pending at the broken initialization boundary.

## Remaining differences

The website validates citation numbers and rejects a factual generation without a citation, an additional fail-closed check beyond the notebook. Browser/source excerpts are redacted; raw source is used only for embeddings. Network latency, provider model updates, cross-platform numeric tolerance, and model nondeterminism may change wording. No exact generated-text parity is claimed.

Container scale-down can cause a fresh runtime index build. The canonical source/model persist in deployment artifacts and private configuration. See [Vercel Container Runtime documentation](https://vercel.com/docs/functions/runtimes/container).

