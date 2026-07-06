# Advanced RAG Pipeline in Langflow — Build Guide

Adds pre-retrieval query optimization (HyDE), semantic chunking, and post-retrieval reranking on top of the Naive RAG pipeline. Verified against this Langflow install's actual component catalog — a few names/behaviors differ from generic course material, noted below as Gotchas.

## 1. Components to add

| # | Component | Category | Purpose |
|---|-----------|----------|---------|
| 1 | **Read File** | Files & Knowledge | Loads the source document |
| 2 | **Type Convert** | Processing | Bridges Read File's `Message` output to `Data` — see Gotcha #1 |
| 3 | **Semantic Text Splitter** | Processing (langchain_utilities) | Splits on semantic boundaries instead of fixed character counts |
| 4 | **Embedding Model** (Ollama/OpenAI/Gemini — match whatever you used before) | Models | Feeds both the splitter and the vector store |
| 5 | **Chat Input** | Input/Output | User's raw question |
| 6 | **Prompt Template** (HyDE) | Models & Agents | Asks the LLM to write a hypothetical answer to the question |
| 7 | **Language Model** (HyDE generator — any provider) | Models | Generates the hypothetical answer text |
| 8 | **Chroma DB** (or your existing vector store) | Vector Stores | Ingests chunks; also acts as the "retriever" — no separate Retriever component exists in this Langflow version |
| 9 | **Cohere Rerank** | Models (cohere) | Re-scores the over-fetched candidates, keeps only the best few |
| 10 | **Parser** | Processing | Converts Cohere's reranked results (a list) into plain text — same as Naive RAG Gotcha #2 |
| 11 | **Prompt Template** (Answer) | Models & Agents | Combines reranked context + the ORIGINAL question |
| 12 | **Language Model** (Answer generator) | Models | Generates the final grounded answer |
| 13 | **Chat Output** | Input/Output | Displays the answer |

**Do NOT reuse Naive RAG's ingest/retrieve-in-one-node pattern here without separating them** — same re-ingestion-on-every-query risk as Naive RAG Gotcha #7 applies.

## 2. Configure each node

- **Read File** → upload your source document.
- **Type Convert** → Output Type: **JSON** (this is what carries `Data` semantics forward).
- **Semantic Text Splitter**:
  - **Data Inputs**: from Type Convert.
  - **Embeddings**: wire in your Embedding Model here too (it's required — the splitter uses embedding similarity between sentences to decide where to break chunks).
  - **Breakpoint Threshold Type**: `percentile` (per the reference material).
  - Leave **Breakpoint Threshold Amount** / **Number of Chunks** at defaults unless you want to tune sensitivity.
- **Embedding Model** → same provider/model/dimensions you used for Naive RAG, so it matches your existing vector store's collection dimension if reusing one.
- **Chroma DB**:
  - **Persist Directory**: required, e.g. `./chroma_db_advanced`.
  - **Number of Results**: **20** (over-fetch candidates for reranking — this is the diagram's "k=20").
  - **Collection Name**: give it a fresh name distinct from any Naive RAG collection.
- **HyDE Prompt Template** → Template:
  ```
  Write a short, plausible, hypothetical answer to the following question,
  even if you're not sure it's correct. This will be used only to improve
  document retrieval, not shown to the user.

  Question: {question}
  ```
  Typing `{question}` auto-creates a `question` input field on this node.
- **HyDE Language Model** → any provider you have working credentials for (Groq/Gemini/OpenAI). Keep temperature low-ish (0.3–0.5) — it just needs a plausible-sounding guess, not creativity.
- **Cohere Rerank**:
  - **Top N**: **4** (matches the diagram's "top-20 → best 4").
  - **Cohere API Key**: paste directly, or if it defaults to `load_from_db: true`, flip it to type-a-value-directly mode (same trap as Naive RAG Gotcha #4).
  - **Model**: `rerank-english-v3.0` (or `rerank-multilingual-v3.0` if your docs aren't English).
- **Parser** → **Mode: Stringify** (required — Cohere's `reranked_documents` output is a list, and Parser's default "Parser" mode rejects lists, identical to Naive RAG Gotcha #2).
- **Answer Prompt Template** → Template:
  ```
  Use ONLY the following context to answer the question. If the answer is
  not contained in the context, say you don't have that information — do
  not guess.

  Context: {context}
  Question: {question}
  ```
- **Answer Language Model** → `gpt-4o` per the reference, but use whatever provider currently has working quota for you (temperature `0.2` for grounded, low-variance answers).

## 3. Wire the connections

Ingestion path:
```
Read File.Raw Content        →  Type Convert.Input
Type Convert.JSON Output     →  Semantic Text Splitter.Data Inputs
Embedding Model.Embeddings   →  Semantic Text Splitter.Embeddings
Semantic Text Splitter.Chunks →  Chroma DB.Ingest Data
Embedding Model.Embeddings   →  Chroma DB.Embedding   (a second Embedding Model node, or the same one's output split to both — Langflow allows one output to fan out to multiple inputs)
```

Pre-retrieval (HyDE) path:
```
Chat Input.Message  →  HyDE Prompt Template.question
HyDE Prompt Template.Prompt  →  HyDE Language Model.Input
HyDE Language Model.Model Response  →  Chroma DB.Search Query   ⚠ hypothetical answer, NOT the raw question
```

Post-retrieval (rerank) path:
```
Chat Input.Message        →  Cohere Rerank.Search Query   (the ORIGINAL question, for relevance scoring)
Chroma DB.Search Results  →  Cohere Rerank.Search Results
Cohere Rerank.Reranked Documents  →  Parser.Input
Parser.Parsed Text        →  Answer Prompt Template.context
```

Answer generation path:
```
Chat Input.Message           →  Answer Prompt Template.question   ⚠ the ORIGINAL question, NOT HyDE's hypothetical text
Answer Prompt Template.Prompt →  Answer Language Model.Input
Answer Language Model.Model Response    →  Chat Output.Inputs
```

**The two places marked ⚠ are the most common mistake when building this by hand**: HyDE's hypothetical answer should only ever be used to *search* the vector store — both the reranker's relevance scoring and the final answer prompt should use the user's real, original question. Wiring HyDE's output into either of those by mistake will make the model answer as if the hypothetical guess were the real question.

## 4. Test it

Click **Play** → **Playground** → ask a question. Compare against Naive RAG using the QA scenarios below.

---

## Gotchas specific to this build (on top of everything in the Naive RAG guide)

1. **Semantic Text Splitter doesn't accept `Message` directly.** Its `Data Inputs` field only accepts `Data`/`JSON`, same class of type-mismatch as Naive RAG Gotcha #1 (`RecursiveCharacterTextSplitter` vs `SplitText`). Fix: insert a **Type Convert** node (Output Type: JSON) between Read File and the splitter.

2. **Semantic Text Splitter requires its own `Embeddings` input.** Unlike `SplitText`, it can't chunk without an embedding model wired in directly — it needs to compute sentence-to-sentence similarity to find semantic breakpoints. Don't forget this connection or the node will error as missing a required input.

3. **Cohere Rerank's output is a list — Parser needs Stringify mode.** Identical failure mode to Naive RAG Gotcha #2 (`List of Data objects is not supported`). Set Parser's Mode to **Stringify** before wiring it after Cohere Rerank.

4. **Don't let HyDE's hypothetical answer leak into the final answer prompt.** It's easy to wire `Chat Input` once and reuse it everywhere, but HyDE's whole purpose is pre-retrieval only — the reranker and the answer-generation prompt must both use the *original* question, not the model's guess. Double-check both `question` fields trace back to `Chat Input`, not to the HyDE Language Model's output.

5. **No standalone "Retriever" component exists in this Langflow version.** The vector store component (Chroma DB, Astra DB, etc.) *is* the retriever — set `Number of Results` on it directly (20 here, for over-fetching before rerank) rather than looking for a separate node.

6. **Two different embedding-related dimension traps stack here.** If your Semantic Text Splitter's embedding model differs in dimension from your Chroma DB's embedding model, nothing errors loudly — the splitter just does its own semantic-similarity math independently of the vector store, so a mismatch there is silent and only shows up as "chunking looks a bit off," not a hard error like Naive RAG Gotcha #3. Keep both pointed at the same embedding model/provider to avoid subtle inconsistency.

---

## QA Testing

| ID | Scenario | Test query used | Result |
|----|----------|------------------|--------|
| T01 | **Reranking precision test** | *"How long until my account gets locked, and what unlocks it early?"* | ✅ **Pass.** Reranking correctly isolated Section 1.5 (Account Lockout Policy) — 5 consecutive failures, 15-minute lockout, early-unlock via password reset — over superficially similar security-adjacent noise (Login Flow, Session Timeout) that otherwise crowds the k=20 candidate pool. |
| T02 | **HyDE degradation / ambiguous query test** | *"What happens after repeated failures?"* | ⚠️ **Initially failed, then fixed.** First run answered only the login-lockout interpretation, silently dropping the equally valid payment-failure interpretation (Section 3.3) — a retrieval bias issue, not hallucination (the content existed but never reached the model). After tuning, the same query correctly identified both interpretations and answered each with accurate details. |
| T03 | **Reranking latency test** | *"What are the pricing tiers and how much do they cost?"* | ℹ️ **Measured, not yet compared against a no-rerank baseline.** Real per-node timings observed: Cohere Rerank ~1.6s, Answer Language Model ~10.1s (gemini-3.5-flash), Chat Output ~0.3s. Rerank itself is a small fraction of total latency here — the answer-generation LLM call dominates. Still need a true A/B (with vs. without Cohere Rerank in the path) to isolate reranking's specific cost. |
| T04 | **Semantic chunking edge cases** | *"What are the pricing tiers and how much do they cost?"* | ✅ **Pass, with a caveat.** The pricing table (Section 3.2) came back with no cross-row contamination — no tier's price got paired with another tier's overage cost. Caveat: full-chunk inspection showed the semantic splitter is currently under-segmenting (merging entire adjacent sections into oversized chunks, likely because **Number of Chunks** is set to `5` for a 6-section document), so this pass can't yet be fully credited to *good* semantic boundary detection versus everything simply landing in one giant chunk together. Needs re-verification after chunking sensitivity is tuned. |
| T05 | **Parent-child retrieval accuracy** | — | ⬜ **Not implemented.** No parent-document retriever component exists in this build. Would require storing child chunks for search while returning their parent document's full text — a distinct pattern beyond what's built here. |

**Additional scenarios run (not part of the original T01–T05 set):**

| Query | Purpose | Result |
|---|---|---|
| *"What happens if my payment fails?"* | Simple baseline — confirm the pipeline works at all | ✅ Pass — correctly surfaced Section 3.3 (grace period, retry schedule on days 1/3/6) |
| *"What is the maximum file upload size for attachments?"* | Negative/hallucination test — nothing in the doc covers this | Not yet run — expected behavior is an explicit "I don't have that information," not an invented number |

**Documentation-drift finding:** this guide originally specified Cohere Rerank's `top_n=4` (Section 2, per the reference design). Cross-checking against the actual exported flow (`LangFlow_Export_JSON_File.json`) found it configured to `top_n=6` instead — a real-world example of a config/documentation consistency test, and a reminder to verify against the live flow export rather than trusting build notes once a flow has been tuned post-build.

## RAG Testing Taxonomy (general reference)

RAG testing differs from typical app testing because there are **two independent failure surfaces** — retrieval (did we find the right chunks?) and generation (did the model use them correctly?) — and a bug in either produces the same visible symptom: a wrong answer. Good RAG testing isolates *which* layer actually failed.

### 1. Retrieval quality
- **Precision test** — does it return the *right* chunks, not just *some* chunks? (T01 above)
- **Recall test** — does it find *all* the relevant chunks? Naive RAG's "What are the login test cases?" returning only 4 of 10 real ones was a recall failure, fixed by raising `k` and adding an explicit "list everything" instruction.

### 2. Query robustness
- **Ambiguous query test** — does it handle a question with 2+ valid interpretations, or silently commit to one? (T02 above)
- **Out-of-scope / negative test** — does it admit "I don't know" instead of hallucinating when the answer genuinely isn't in the document?

### 3. Chunking integrity
- **Structured content edge case** — do tables, code blocks, and lists survive chunking intact? (T04 above)
- **Boundary/split test** — does content get lost between two adjacent chunks? Naive RAG's TC-LOGIN-002 fell into a gap neither chunk's overlap region covered — fixed by increasing `chunk_overlap`.

### 4. Data hygiene
- **Duplicate/ingestion test** — does re-running ingestion create duplicate vectors that skew retrieval? Found here: the same chunk appearing 5–7× in the k=20 candidate pool because the ingest node was still wired into the live query path — an infrastructure bug that silently poisons every other test until fixed.
- **Embedding/dimension consistency test** — do ingestion-time and query-time embeddings use the same model/dimension? Naive RAG hit this directly switching from OpenAI to Gemini embeddings without resetting the collection — searches silently returned nothing, no error raised.

### 5. Non-functional
- **Latency test** — does an added step (reranking, HyDE) cost an acceptable amount of time? (T03 above)
- **Consistency test** — does the same question asked twice return materially the same answer? LLM temperature and retrieval nondeterminism can make "worked when I tested it" different from "works reliably."

**The recurring pattern across nearly every issue found in this project:** the error message rarely names the actual failing layer. `list index out of range` turned out to be a missing wire, not a broken component. A correct-*looking* answer turned out to be lucky given an oversized merged chunk, not evidence of good chunking. The habit worth building: whenever an answer looks wrong *or* suspiciously right, trace the actual retrieved chunks before trusting either verdict.