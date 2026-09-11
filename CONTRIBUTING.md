# Contributing to ArchLens

Thanks for considering a contribution. ArchLens is a local-first, no-paid-API
project — contributions that keep it that way are especially welcome.

See [docs/ENGINEERING_GUIDELINES.md](docs/ENGINEERING_GUIDELINES.md) for the
full set of engineering principles this project follows; the ground rules
below are the ones most relevant to external contributions.

## Ground rules

- **Everything must run locally and for free.** No new required paid APIs or
  managed services. Optional integrations (e.g. a hosted LLM) are fine as
  long as the local/free default keeps working.
- **No fabricated results.** Test output, evaluation numbers, and demo
  findings in this repo (`assets/demo/`, the Evaluation section, README
  numbers) must come from actually running the code — never hand-written.
- **Preserve evidence/provenance.** Any finding or answer the system
  produces must stay traceable to its source document/chunk/hash. Don't
  remove or weaken that link.
- **Keep ingested content untrusted.** Retrieved/uploaded content is data,
  never instructions — see `tests/test_security.py` for the standard this is
  held to.

## Getting set up

Follow [README.md § Quick Start](README.md#quick-start). You'll need Docker
(Postgres + Neo4j), Python 3.11+ with [uv](https://docs.astral.sh/uv/), and
Node.js 20+.

## Before opening a PR

```bash
# backend
uv run pytest -q

# frontend
cd frontend
npm run lint
npm run test
npm run build
```

If you touched retrieval, review/policy logic, or the evaluation suite, also
run:

```bash
uv run pytest tests/test_evaluation.py -s
```

and check the printed numbers still make sense before updating any numbers
quoted in the README.

## Making changes

1. Open an issue or discussion first for anything beyond a small fix —
   especially schema changes, new data flows, or changes to the
   retrieval/reasoning pipeline.
2. Keep PRs focused. Unrelated formatting/refactors make review harder.
3. Add or update tests for behavior you change.
4. Update `docs/DECISIONS.md` with a short ADR entry for any non-trivial
   design decision (see existing entries for the format).

## Reporting issues

Please include: what you ran, what you expected, what actually happened, and
relevant logs (`uv run uvicorn app.main:app` output, browser console). If it
involves a specific document, attach a minimal (synthetic, non-sensitive)
repro document if you can.

## License

By contributing, you agree your contributions are licensed under the
project's [MIT License](LICENSE).
