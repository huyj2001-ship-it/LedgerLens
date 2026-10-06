# LedgerLens

> Ask Europe's annual reports hard questions. Get numbers that cite their source and are graded automatically.

LedgerLens is an agentic RAG system that answers multi-company, multi-year questions over real
European annual reports (ESEF filings). It searches long reports, reads tables, converts currencies
with ECB reference rates, computes ratios and cites every number back to the source document.

Because ESEF reports embed machine-readable XBRL tags, every numeric answer can be graded exactly
against the companies' own tagged figures. The tags are used **only as an answer key**: the agent
never sees them.

**Status:** early development. See the [roadmap](#roadmap).

## Why this project

| Requirement | How LedgerLens meets it |
|---|---|
| Real data | Annual reports of listed EU companies from [filings.xbrl.org](https://filings.xbrl.org) |
| Verifiable answers | XBRL tags give exact gold values, so no LLM judge is needed for numbers |
| Genuinely agentic | Questions need several filtered lookups, FX conversion and arithmetic |
| Easy to understand | "Which of these companies grew revenue fastest?" needs no domain training |

## Roadmap

- [ ] Data ingestion and answer key (iXBRL parser, ECB FX rates)
- [ ] Hybrid retrieval and naive RAG baselines
- [ ] LangGraph agent with deterministic verification
- [ ] API, UI, observability and safety evaluation
- [ ] Fine-tuned local extractor (QLoRA)

## Design decisions

Architecture decisions are recorded as ADRs in [`docs/adr`](docs/adr).

## License

Apache-2.0. Annual reports are the property of the respective companies and are not redistributed
in this repository.
