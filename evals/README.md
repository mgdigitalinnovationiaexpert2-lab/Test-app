# MG Benchmark / Model League

Synthetic fixtures cover GENERAL, MANAGEMENT, HR, PROCESS, DATA, MARKETING, PRODUCTION,
IT_CODING, LIFE_OS_STUDY, DOCUMENT_ANALYSIS and PERSIAN. This small starter set validates
the framework and is insufficient to certify a production model.

```powershell
python -m mg_ai.evals
python -m mg_ai.evals --responses reports/candidate-answers.json --output reports/candidate-eval.json
```

Without responses the runner labels results `fixture_self_test`, not a model benchmark.
An offline answer JSON maps every fixture ID to an answer string; missing/extra IDs fail.
Generated code is never executed. Substring scoring is only a deterministic smoke check.
Human review is mandatory: matching words does not establish correctness or quality.

## Champion/challenger workflow

1. Review a disabled challenger's free entitlement/privacy. Use synthetic data in an isolated
   evaluation config with a client/model allowlist. Runtime excludes challenger-role rows.
2. Record candidate/model/provider, date, config hash, fixture version, sampling parameters,
   synthetic answers, latency, token usage and success/failure rate. Reports are ignored.
3. Review applicable dimensions: answer quality, correctness, Persian quality, coding quality,
   tool calling, structured reliability, hallucination/error, latency, cost, success rate.
   Normalize quality to 0..1; latency in ms and cost in USD. Unmeasured dimensions are null.
4. Compare paired champion/challenger fixtures with blind human review. Require no security/
   privacy regressions and reliable tools/schema for claimed capabilities. Default category
   thresholds .6 (.8 strong) do not establish production quality on starter fixtures alone.
5. Save a reviewed decision and provenance, update task scores/role/tier/capabilities, and
   optionally route champion. Promotion is manual; no live sampling or automatic promotion.

Future anonymized datasets need owner review, identifier removal, secret checks and a dataset
card documenting provenance, consent, redaction, intended use and retention. Never commit
confidential production data. Extend domain/adversarial fixtures before quality claims.
Obtaining candidate answers is a separate explicit free-only step; the offline runner never
spends money or calls a provider implicitly.
