# Free candidate review queue — 2026-09-09

The controlled refresh reads the official OpenRouter catalog and accepts only explicit
`:free` identifiers whose every reported pricing field is finite zero. This is discovery
evidence, not account entitlement, privacy approval, capability proof or an MG benchmark.
All registry proposals remain disabled and unapproved; there is no current Champion.

| Disabled target | Why it is queued | Qualification state |
|---|---|---|
| `cohere/north-mini-code:free` | Advertises tool parameters; coding candidate | NOT_BENCHMARKED |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | Large reasoning candidate | NOT_BENCHMARKED |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | Advertises tools and image input | NOT_BENCHMARKED |
| `nvidia/nemotron-3-super-120b-a12b:free` | Reasoning/workhorse candidate | NOT_BENCHMARKED |
| `google/gemma-4-26b-a4b-it:free` | Persian/general workhorse candidate | NOT_BENCHMARKED |
| `google/gemma-4-31b-it:free` | Persian/general workhorse candidate | NOT_BENCHMARKED |
| `nex-agi/nex-n2.5-pro:free` | Newly discovered general candidate | NOT_BENCHMARKED |
| `openrouter/free` | Nondeterministic model selection | REJECTED as Champion |

MiniMax M3 and the earlier M2.7 were removed from the free catalog between snapshots, so
they are not benchmark targets now. GLM 5.2 is absent from the current explicit free list.
Catalog-advertised parameters and modalities are stored separately from verified
capabilities. Popularity or a model name never grants CODE, REASONING, PERSIAN, VISION,
TOOL_CALLING, STRUCTURED_OUTPUT, LONG_CONTEXT or confidential-data eligibility.

Every target still has unreviewed coding, reasoning and Persian suitability, unknown
account capacity, no MG score, disabled health and unreviewed privacy. Zero latency/failure
defaults mean unmeasured. Unknown retention/training policy never qualifies confidential
Portal work.

Promotion remains: discovered → disabled → synthetic capability probes → MG route benchmark
→ qualitative review → privacy and zero-cost review → owner-approved Challenger/Champion
→ enabled. `python -m mg_ai.discovery` refreshes recommendations and detects removed,
free-to-paid and metadata changes; it never edits the registry or promotes a model.
