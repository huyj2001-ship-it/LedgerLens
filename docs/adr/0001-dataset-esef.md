# ADR-0001: Use ESEF annual reports as the corpus

- **Status:** accepted

## Context

The project needs a corpus that is real, legally reusable, long enough that retrieval is genuinely
hard, and comes with a way to check answers objectively. Hand-written answer keys do not scale and
are themselves a source of error; LLM judges are biased and hard to defend for numeric answers.

Since 2021 the European Single Electronic Format (ESEF) requires listed EU companies to publish
their annual financial reports as Inline XBRL: an XHTML document in which the figures of the primary
financial statements are tagged with a concept (`ifrs-full:Revenue`), a period, a unit and a
precision. [filings.xbrl.org](https://filings.xbrl.org) collects these filings and serves both the
XHTML report and an xBRL-JSON rendering of the tagged facts through a JSON:API.

## Decision

Use ESEF annual reports of large non-financial EU companies (FY2022 to FY2025) as the corpus.
Use the XBRL facts **only as an answer key**: they are stripped from the indexed text and live in a
separate package (`ledgerlens_eval`) that the runtime cannot import.

## Alternatives considered

| Option | Why not |
|---|---|
| Eurostat / Our World in Data | Clean and verifiable, but the documents are short; the RAG part would be thin |
| FinanceBench (SEC 10-K) | Non-commercial licence; only 150 open questions; US companies |
| EU legislation (EUR-Lex) | Answers need a hand-written legal oracle that nobody can verify independently |
| Wikipedia multi-hop QA | Saturated benchmark; heavy training-data contamination |

## Consequences

- Every numeric answer can be graded exactly and automatically, with tolerances derived from the
  tag's declared precision.
- Reports are long (hundreds of pages, more than 10 MB of XHTML) with complex tables, which makes
  chunking and retrieval a real problem rather than a toy one.
- An obvious objection is "why not just query the tags?". Tags cover only the primary statements,
  most enterprise documents have no tags at all, and the structured route is reported as an upper
  bound in the evaluation.
- Reports are company documents: the repository ships a downloader and a manifest, never the files.
- Banks and insurers are excluded because they do not report a comparable `Revenue` line.
