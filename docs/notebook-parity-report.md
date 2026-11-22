# Notebook parity verification

Status: source configuration repaired; real production model and matching index initialized. Live evaluation revealed missing citations in four responses; a bounded citation retry is being verified.

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

16 Python checks and 6 Node checks passed. The independent comparator ran reviewed functions from the supplied notebook, not a reimplementation of its retrieval oracle. Records and chunks were equal. It built two independent Chroma collections using a shared actual encoder; all ranks/IDs/scores matched within 1e-6. Initial Groq request payloads were compared with deterministic completion stubs; these are not live LLM quality tests.

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

Both production secrets are configured without displaying their values. The deployed MiniLM/Chroma index fingerprint matched the independent local reference and Groq accepted the key. The 12 live ranking/citation/refusal checks passed after structured citation repair, but a follow-up request hit the provider rate limit and manual review found unsupported renewal extrapolation in a numbered answer. Final verification is pending the stronger grounding guard described below; a successful numbered citation is not alone proof of semantic support.

## Website evidence guard beyond the notebook

The notebook's initial generation request is preserved. Every non-refusal draft gets one additional structured evidence check with the same current passages, Groq model, temperature 0, and 700-token limit. Each claim must identify a current passage and copy an exact supporting quote. The server checks quote occurrence and passage bounds, merges identical claims, and renders only model-selected references. The verifier must refuse an entire multi-part question when any requested part lacks evidence. Invalid output fails closed. This adds latency and quota usage and is an explicit generation-path difference from the notebook. Groq rate limits now return HTTP 429 and Retry-After, never a keyword or stored-answer substitution.

The source/index/chunk/ranking path and first generation payload are compared separately from this additional website safeguard. Model verification can still make semantic mistakes; quote occurrence is a check of provenance, not a formal proof of entailment. No exact generated-text parity is claimed.

## Browser checks

Desktop 1280px and mobile 390px checks passed for real OPAC answers, clickable worksheet references, mascot loading, no horizontal overflow, mobile navigation, and New Chat clearing all message articles. Final-generation answers will be checked again after the guard deploys. Prepared/private source files remain outside public/ and return 404.

## Deployment limits

The Python container packages the model at build time. Source integrity is checked before initializing the model/index. Temporary Chroma storage is a reconstructible cache from deployment source plus private configuration, not the only source of truth. Scale-down can increase cold-start latency. Provider quota can limit bursts of evaluation requests; the live evaluator supports pacing and honors Retry-After.

References: [Vercel Container Runtime](https://vercel.com/docs/functions/runtimes/container), [Groq strict Structured Outputs](https://console.groq.com/docs/structured-outputs).
