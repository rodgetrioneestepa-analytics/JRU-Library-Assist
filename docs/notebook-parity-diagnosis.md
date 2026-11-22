# Diagnosis before parity corrections

Reference: `PewPewPew_Final_RAG_Chatbot_Conversational_Fixed.ipynb` and the supplied `CONSOLIDATED FAQs for VLA.xlsx`.

| Component | Reference notebook | Website before this correction |
|---|---|---|
| Source | Full 14-sheet workbook; separate wide/topic parsers | Same workbook fingerprint and 293 deduplicated records; source is not incomplete |
| Embeddings | all-MiniLM-L6-v2; normalized queries/documents | Deployed Node route does not compute embeddings |
| Retrieval | ChromaDB cosine; recursive FAQ-aware 800/100 chunks; top 3; similarity floor 0.35 | BM25 keyword ranking over whole FAQ records, plus a custom definition-ranking bonus |
| Generation | Groq openai/gpt-oss-20b, temperature 0, 700 completion tokens | No production GROQ_API_KEY configured at inspection; returns stored FAQ text |
| Backend connection | Full Python pipeline | No production RAG_BACKEND_URL configured at inspection |
| Conversation | Last six messages; Groq standalone rewrite followed by fresh retrieval | Lexical history concatenation without a key; Groq rewrite only if a key is present |
| Citations | Genuine numbered passages and worksheet references | API discards source details; browser removes citation markers |
| Refusal | Exact notebook refusal | Browser replaces it with shorter wording |
| Record handling | Raw source records indexed; payment/account text redacted before LLM | Prepared records redacted before embeddings, potentially changing some vectors |
| Review flags | Notebook review reasons | Simplified Boolean flag |
| Persistence | Rebuilt Chroma collection for configuration | Local cache identity misses explicit configuration/version fields; deployed app does not use this index |

The fundamental cause is an execution-path mismatch: copying notebook prompts and Python source into the repository did not make the deployed website execute that pipeline. The earlier local Chroma tests established local semantic retrieval only, not production parity or live Groq generation.

## Correction requirements

Remove the keyword/stored-answer fallback. Serve the same Python RAG path, preserve the notebook's source formatting and prompt/history rules, restore citations and the exact refusal, and fail clearly when configuration/model/index/provider access is unavailable. Keep the interface and hide bulk dataset inventories. Validate all 12 notebook evaluation questions against an independent reference built from the actual notebook functions before claiming parity.

The supplied workbook filename differs from the notebook's configured `(4)` suffix; the corrected loader must use the actual supplied filename. Canonical source/index artifacts must persist in the deployment or durable storage; temporary runtime copies must never become the only source of truth.
