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

## QA Test Scenarios — Advanced RAG

| ID | Scenario | What to verify |
|----|----------|-----------------|
| T01 | **Reranking precision test** | Run the same query with `k=4` (no rerank — temporarily bypass Cohere) vs `k=20` + rerank. The reranked version should surface more relevant chunks. |
| T02 | **HyDE degradation test** | Try a deliberately vague/ambiguous query. Confirm HyDE's hypothetical guess doesn't drift so far semantically that retrieval gets *worse* than just embedding the raw question would have. |
| T03 | **Reranking latency test** | Compare response time with vs without Cohere Rerank in the path. Expect roughly +200–500ms; confirm that's acceptable for your use case. |
| T04 | **Semantic chunking edge cases** | Test with code snippets, tables, or mixed-language content. Verify the semantic splitter doesn't cut a code block or table row in half — a real risk since it isn't token-count-aware in the way `chunk_size` is. |
| T05 | **Parent-child retrieval accuracy** | Not implemented in this build (no parent-document retriever component was added) — if you need this, it requires an additional pattern beyond what's here: storing child chunks for search but returning their parent document's full text. Flag as a follow-up if needed. |


===========================
1. Simple baseline (confirm it works at all):


What happens if my payment fails?
Should surface Section 3.3 (Failed Payment Handling — grace period, retry schedule).

2. Ambiguous query (tests T02 — HyDE degradation):


What happens after repeated failures?
This is deliberately vague — it could match Account Lockout Policy (login failures) or Failed Payment Handling (payment retries). Watch which one HyDE's hypothetical answer steers retrieval toward, and whether reranking corrects it if HyDE guesses wrong.

3. Precision test (T01 — needs rerank to matter):


How long until my account gets locked, and what unlocks it early?
Tests whether reranking correctly prioritizes Section 1.5 (Account Lockout Policy) over superficially similar security-adjacent chunks (1.1 Login Flow, 1.3 Session Timeout) that would otherwise crowd the top-20.

4. Structured content edge case (T04):


What are the pricing tiers and how much do they cost?
Checks whether the semantic splitter kept the pricing table (Section 3.2) intact as one coherent chunk instead of fragmenting it row-by-row.

5. Something not in the doc at all (sanity check for hallucination):


What is the maximum file upload size for attachments?
Nothing in the doc covers this — the answer should say it doesn't have that information, not invent a number


=============================

Naive RAG (what you built first)

Chat Input → Vector Store (k=4) → Parser → Prompt → LLM → Chat Output
One retrieval pass: the raw user question is embedded and searched directly, no optimization.
Fixed-size chunking: chunk_size=1000 / chunk_overlap=200 — splits by character count, ignoring meaning.
No filtering: whatever top-k comes back from the vector store goes straight into the prompt, unranked beyond raw similarity score.
Weakness we found empirically: ambiguous queries (like "What are the login test cases?" hitting only 4 of 10 real ones) or content split awkwardly across a fixed-size chunk boundary (TC-LOGIN-002 getting cut in half) — the pipeline has no mechanism to notice or correct either problem.
Advanced RAG (what you just built)

Chat Input → HyDE → Vector Store (k=20, over-fetch) → Cohere Rerank (→4) → Parser → Prompt → LLM → Chat Output
Three additions, each targeting a specific Naive RAG weakness:

HyDE (pre-retrieval): instead of embedding the raw question, an LLM first writes a hypothetical answer, and that gets embedded/searched instead. Hypothetical answers read more like the actual document content than a terse question does, so retrieval targets the right neighborhood in vector space more reliably — you saw this matter directly on the ambiguous "What happens after repeated failures?" query.
Semantic chunking (pre-retrieval): splits on meaning-shifts instead of a fixed character count. In theory this keeps related ideas together and avoids the "cut mid-sentence" problem Naive RAG had — though we just found yours is currently too coarse (merging entire sections), which is its own new failure mode worth tuning.
Reranking (post-retrieval): over-fetch 20 candidates, then use a dedicated cross-encoder model (Cohere) to re-score and keep only the best 4. This exists because embedding-similarity search and "actual relevance to this question" aren't the same thing — reranking is a second, more precise pass specifically to fix that gap.
The honest trade-off
Advanced RAG isn't strictly "better" — it's more components, more places to misconfigure, and slower/costlier per query (HyDE = one extra LLM call before you even retrieve; reranking = one extra API call after). It buys you real improvements on ambiguous or precision-sensitive queries, but only if every added piece is actually tuned correctly — as you just saw, a badly-tuned semantic splitter can introduce a new problem (oversized chunks) that Naive RAG's dumb-but-predictable fixed-size splitter never had.


=======================

Here's the concrete difference, grounded in what we actually built for each (not just textbook theory):

Naive RAG (what you built first)

Chat Input → Vector Store (k=4) → Parser → Prompt → LLM → Chat Output
One retrieval pass: the raw user question is embedded and searched directly, no optimization.
Fixed-size chunking: chunk_size=1000 / chunk_overlap=200 — splits by character count, ignoring meaning.
No filtering: whatever top-k comes back from the vector store goes straight into the prompt, unranked beyond raw similarity score.
Weakness we found empirically: ambiguous queries (like "What are the login test cases?" hitting only 4 of 10 real ones) or content split awkwardly across a fixed-size chunk boundary (TC-LOGIN-002 getting cut in half) — the pipeline has no mechanism to notice or correct either problem.
Advanced RAG (what you just built)

Chat Input → HyDE → Vector Store (k=20, over-fetch) → Cohere Rerank (→4) → Parser → Prompt → LLM → Chat Output
Three additions, each targeting a specific Naive RAG weakness:

HyDE (pre-retrieval): instead of embedding the raw question, an LLM first writes a hypothetical answer, and that gets embedded/searched instead. Hypothetical answers read more like the actual document content than a terse question does, so retrieval targets the right neighborhood in vector space more reliably — you saw this matter directly on the ambiguous "What happens after repeated failures?" query.
Semantic chunking (pre-retrieval): splits on meaning-shifts instead of a fixed character count. In theory this keeps related ideas together and avoids the "cut mid-sentence" problem Naive RAG had — though we just found yours is currently too coarse (merging entire sections), which is its own new failure mode worth tuning.
Reranking (post-retrieval): over-fetch 20 candidates, then use a dedicated cross-encoder model (Cohere) to re-score and keep only the best 4. This exists because embedding-similarity search and "actual relevance to this question" aren't the same thing — reranking is a second, more precise pass specifically to fix that gap.
The honest trade-off
Advanced RAG isn't strictly "better" — it's more components, more places to misconfigure, and slower/costlier per query (HyDE = one extra LLM call before you even retrieve; reranking = one extra API call after). It buys you real improvements on ambiguous or precision-sensitive queries, but only if every added piece is actually tuned correctly — as you just saw, a badly-tuned semantic splitter can introduce a new problem (oversized chunks) that Naive RAG's dumb-but-predictable fixed-size splitter never had.

I need to learn testing of RAG concepts and types/techniques like Ambiguous query ,Precision test ,Structured content edge case
RAG testing is fundamentally different from typical app testing because there are two independent failure surfaces — retrieval (did we find the right chunks?) and generation (did the model use them correctly?) — and a bug in either one produces the same symptom (a wrong answer). Good RAG testing isolates which layer failed. Here's the taxonomy, grounded in what we actually hit this session:

1. Retrieval quality tests
Precision test — does the system return the right chunks, not just some chunks?

What we did: "How long until my account gets locked, and what unlocks it early?" — passed, because reranking correctly isolated Section 1.5 despite similar-sounding noise (Login Flow, Session Timeout) in the candidate pool.
How to design one: pick a document with 2-3 sections that are topically adjacent but factually distinct, then ask a question only one of them answers.
Recall test — does it find all the relevant chunks, not just the first one it stumbles on?

What we did: "What are the login test cases?" only returning 4 of 10 real ones (Naive RAG) — a recall failure, not a precision failure. Fixed by raising k and adding an explicit "list everything" instruction.
2. Query robustness tests
Ambiguous query test — does the system handle a question with 2+ valid interpretations?

What we did: "What happens after repeated failures?" initially answered only the login-lockout interpretation, silently dropping the payment-failure interpretation. This is a retrieval bias failure, not hallucination — the content existed in the doc but never reached the model.
How to design one: find or write a term that's genuinely overloaded in your domain ("failure," "timeout," "limit") and confirm both meanings are addressed or the ambiguity is at least surfaced.
Out-of-scope / negative test — does it admit "I don't know" instead of hallucinating?

What we planned but haven't run yet: asking about something absent from the doc entirely (e.g. "max file upload size") — the correct behavior is refusal, not invention.
3. Chunking integrity tests
Structured content edge case — do tables, code blocks, and lists survive chunking intact?

What we did: the pricing tiers table came back with no cross-row contamination (Growth's price never got paired with Scale's overage) — a pass, though we couldn't fully attribute it to good chunking vs. accidentally landing inside an oversized merged chunk.
How to design one: put a table or code block near a likely chunk boundary and ask a question that requires reading the whole structure — a single fragmented row/line means the splitter cut through it.
Boundary/split test — does content get lost between two adjacent chunks?

What we did: TC-LOGIN-002 in Naive RAG fell into a gap where neither chunk's overlap region fully covered it — the fix was increasing chunk_overlap.
4. Data hygiene tests
Duplicate/ingestion test — does re-running ingestion create duplicate vectors that skew retrieval?

What we did: found Astra DB returning the same chunk 5-7× in the k=20 candidate pool, because the ingest node was still wired into the live query path. This is an infrastructure bug, not a model or prompt bug — worth checking early since it silently poisons every other test above.
Embedding/dimension consistency test — do all embedding calls (ingestion-time and query-time) use the same model/dimension?

What we did: hit this directly switching Naive RAG from OpenAI to Gemini embeddings without also resetting the collection — searches silently returned nothing, no error.
5. Non-functional tests
Latency test — does an added step (reranking, HyDE) cost an acceptable amount of time?

Still on your list as T03 — worth actually timing it with vs. without reranking rather than guessing.
Consistency test (not in your list yet, worth adding) — does the same question asked twice return materially the same answer? LLM temperature and retrieval nondeterminism can make "works when I tested it" not the same as "works reliably."

The pattern across almost everything we found: the error message rarely tells you which layer actually failed. "List index out of range" turned out to be a missing wire, not a broken component. A "correct-looking" answer turned out to be lucky given an oversized chunk, not evidence of good chunking. The habit worth building is: whenever an answer looks wrong or suspiciously right, trace the actual retrieved chunks before trusting either verdict — exactly what we did with the /build events stream throughout this session.

Want me to turn this into a saved reference doc in your project, or keep it as something you refer back to in this conversation?