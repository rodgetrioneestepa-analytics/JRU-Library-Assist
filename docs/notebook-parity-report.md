# Notebook parity verification

Result: production is working with live Groq generation. All 12 evaluation cases, four conversational requests, and browser checks passed. This verifies the core retrieval path and evidence-supported behavior; it does not claim identical generated wording.

## Original causes

The website previously ran BM25 over whole FAQ records and returned stored answers. It did not execute the notebook MiniLM/Chroma path. Production lacked the Python connection and Groq key, browser rendering removed citations and changed the refusal, review flags differed, and payment redaction happened before embedding. The full workbook was already present.

## Applied configuration

- All 14 original worksheet names/order retained: 542 parsed rows, 293 deduplicated records, 296 chunks. Wide/topic parsing, continuation rows, duplicate provenance, and conflict flags match the notebook.
- Normalized sentence-transformers/all-MiniLM-L6-v2 on CPU; Chroma cosine; RecursiveCharacterTextSplitter 800 characters, 100 overlap, top 3, minimum similarity 0.35 (active B).
- Groq openai/gpt-oss-20b; temperature 0; initial completion budget 700. Follow-up rewriting uses 450 tokens and six messages. Initial prompts and request settings match the notebook.
- Workbook SHA256: `87c3407927e546fa50682b6c92052d34ee5f33221f189d18bd274b6646cb1adb`.

The published source is sanitized. One ignored/private override restores original text only for notebook-equivalent embeddings; evidence and browser excerpts are redacted. The source hashes are checked before indexing. The deployment packages model weights and prepared source; temporary Chroma storage is a reconstructible cache. Index identity includes source, configuration, chunks, weights and library versions. No keyword/stored-answer fallback remains.

## Main changes

| Files | Result |
|---|---|
| rag_backend/core.py | Exact workbook parsing, deduplication, source integrity, versioned index, normalized retrieval. |
| generation.py, service.py, notebook_spec.json | Notebook prompts/settings, guarded rewrites, fresh retrieval, exact refusals and real passage citations. |
| app.py, serve.py, Dockerfile.vercel, vercel.json | Python production runtime, readiness checks, clear unavailable/rate-limit responses. |
| lib/chat.mjs | Development proxy only; lexical implementation removed. |
| public/app.mjs, chat-only.css | Preserve answers/citations, clickable worksheet excerpts, session reset; existing JRU interface retained. |
| prepare-chatbot.py, evaluate-parity.py, tests | Reproducible preparation and independent notebook comparison, paced live evaluation. |

## Verification

17 backend and 6 frontend checks passed. The local comparator ran reviewed functions from the supplied notebook and built independent Chroma collections with a shared actual encoder. Records and chunks were equal; all 12 rankings/scores matched within 1e-6. Initial Groq payloads matched using deterministic stubs; these local stubs were not treated as live generation tests.

Production returned the same index fingerprint as the local reference. Live rankings matched within 1e-4. Every returned citation selected an actual current passage; unsupported requests used the exact refusal. The final live evaluation used real Groq and paced requests to respect provider limits.

| Case | Question tested | Live result | Gold-record recall@3 |
|---|---|---|---|
| E1 | What does OPAC stand for? | PASS: cited answer | 100% |
| E2 | What are the Main Library's Saturday hours according to the FAQ? | PASS: cited answer | 100% |
| E3 | How many Learning Commons reservations can students make per day? | PASS: cited answer | 100% |
| A1 | What are the online and email ways to renew a library book? | PASS: cited answer | 50% |
| A2 | How does a student pay a library fine at the cashier? | PASS: cited answer | 100% |
| A3 | What should a student do if they left their ID at home? | PASS: cited answer | 100% |
| D1 | What should a student with an overdue book and unpaid fines do about renewal and payment? | PASS: cited answer | 100% |
| D2 | Can a student take a borrowed library laptop into class and install extra workstation software themselves? | PASS: refused | 50% |
| D3 | How long may a student borrow a library laptop and reserve a Learning Commons room? | PASS: refused | 50% |
| U1 | What is the actual Wi-Fi password for JRU LIB3? | PASS: refused | N/A |
| U2 | How many seats are empty in the Main Library right now? | PASS: refused | N/A |
| U3 | Which librarian is physically on duty at this exact moment? | PASS: refused | N/A |

Duplicate records keep their first canonical worksheet reference and all aliases; gold recall is computed using record IDs. The notebook retrieval itself reaches only 50% of its gold records for A1, D2 and D3. A1 is answered from overlapping wide-format evidence. D2 and D3 are refused because the current top-three passages do not establish the entire question. Rankings were not changed to conceal these limitations.

Manual review confirmed OPAC, Saturday 7 AM to 6 PM, one Learning Commons reservation/day, renewal methods, cashier payment/receipt, and the temporary ID permit. The overdue/fines answer now states the documented online-renewal restriction and payment steps without inventing a promise of renewed eligibility.

Conversation checks passed: students borrowing a laptop, faculty follow-up rewritten with laptop context, a switch to OPAC, and a fresh request without history. The faculty answer uses its own newly retrieved eight-hour policy. Browser checks passed at desktop 1280px and mobile 390px: mascot, citations opening real worksheet excerpts, navigation, no horizontal overflow, and New Chat clearing messages. Prepared/private source URLs returned 404.

## Explicit differences and limits

The website adds one structured evidence review after each non-refusal notebook draft. It uses the same current passages, model, temperature and 700-token limit, with low reasoning effort for this extra review. Claims explicitly select valid current passage IDs; identical claims are merged. Strict output can fall back to provider JSON mode while the same server validation remains. This additional step corrected observed uncited and unsupported extrapolations, but adds latency/quota use and is a generation-path difference from the notebook. Passage-ID validation and model review are not formal proofs of semantic entailment.

Groq limits can interrupt bursts; HTTP 429 and Retry-After now give clear retry guidance. Cold instances rebuild the disposable index from durable deployment artifacts/configuration. No exact generated-text parity is claimed. Earlier failed citation/verification runs were corrected and rerun; the final cases above all passed.

Verified runtime commit: `e5a04bd8b540344296c00eb7b6120f7273a5f10a`. Production deployment: `dpl_BC9jsmjL6Tfy9qwp2v4ScUADYR2S`.

References: [Vercel Container Runtime](https://vercel.com/docs/functions/runtimes/container), [Groq Structured Outputs](https://console.groq.com/docs/structured-outputs).
