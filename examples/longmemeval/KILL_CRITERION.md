# Kill criterion — open-weight reader on the Brain's memory

Written 2026-09-15, before the gpt-oss:20b run produced any answer.

Thesis under test: the memory is the asset and the model is replaceable; losing the hosted
models does not lose the memory's usefulness.

Setup, fixed in advance: LongMemEval-S, the stratified 100 (LME_SUBSET=100), the Brain's top-5
sessions from qa_log.jsonl unchanged, official reader and judge prompts, one judge for every
reader: gpt-5.1-2025-11-13 (reasoning_effort none). Reference on the same ids and the same judge:
gemini-3-flash-preview 85/100, gpt-6-astra 85/100 (82 correct with retrieval ok, 90 retrievals ok).
Reader: ollama gpt-oss:20b, local, RTX 4050 6 GB + 40 GB RAM, num_ctx 32768, temperature 0.

Verdicts, decided now:
- >= 80/100: thesis holds on this hardware — an open-weight reader keeps the memory useful
  within 5 points of the hosted readers.
- 70-79: measurable degradation — open weight is a usable fallback, not a replacement.
- < 70, or more than 5 reader errors: thesis dead on this hardware class. Report it as such,
  do not change model, context size, prompt or judge and re-run to rescue the number.

Secondary, reported but not deciding: correct when retrieval ok (hosted: 82/90), median seconds
per answer.
