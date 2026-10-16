# Provenance: arabic-rag-pipeline

Scripts and prompts are written by Rashed Atieh. Patterns are adapted from the sources below; no upstream file is copied verbatim.

| Source | Commit | Licence | Files used | What we changed |
|---|---|---|---|---|
| https://github.com/langgenius/dify | `1e3fe6ba9396cdeb348a1f5e428e71c6fb3d2389` | Apache-2.0 with additional conditions (backend patterns used: Apache-2.0 terms) | `api/core/rag/splitter/fixed_text_splitter.py` (separator list), `api/core/rag/index_processor/constant/index_type.py`, `processor/parent_child_index_processor.py`, `api/core/rag/rerank/weight_rerank.py`, `api/core/rag/retrieval/retrieval_methods.py` | Identified the missing Arabic separators and jieba keyword gap; parent-child and weighted-rerank ideas described, not copied; our chunker adds ؟ ، ؛ ۔ handling |
| https://github.com/lfnovo/open-notebook | `a0f6f3081ae06328f0a451b3a3ef2959ca25721d` | MIT (Copyright (c) 2024 Luis Novo) | `prompts/ask/entry.jinja`, `prompts/ask/final_answer.jinja`, `open_notebook/graphs/ask.py`, `open_notebook/utils/chunking.py` | Kept the plan → fan-out → cited answer structure; rewrote prompts for dialect and Arabizi rewriting, bilingual output, refusal and handoff |
| https://github.com/supabase/supabase | `eeae6027d5dc658932c6bd496a8c13e0277b7fdb` | Apache-2.0 | `apps/docs/content/guides/ai/hybrid-search.mdx`, `rag-with-permissions.mdx`, `vector-indexes.mdx` | RRF function adapted: `simple` configuration on an index-normalised column, cosine operator, `allowed_groups` filter in both legs, returned score |
| https://github.com/open-webui/open-webui | `8bd8b4fac5e059578ac0c74b3c18d11139f88b7d` | Open WebUI License (BSD-3-Clause + branding clause) | `backend/open_webui/config.py` (RAG defaults, `DEFAULT_RAG_TEMPLATE` citation rules), `retrieval/utils.py` (whitespace BM25) | Cited defaults as risks; citation rules re-expressed in our prompt |
| https://github.com/unclecode/crawl4AI | `8afd0a68064ff7049303c9f9d037ab6228aac43c` | Apache-2.0 + attribution requirement | `docs/md_v2/core/fit-markdown.md`, `extraction/chunking.md` | Usage notes only; attribution rule carried forward |
| https://github.com/Stirling-Tools/stirling-pdf | `850f2459297d8176c14cb5e1c5f495b088151715` | MIT core | `docs/developer/HowToUseOCR.md`, `controller/api/misc/OCRController.java` (via Repo Card) | OCR options and Arabic pack mounting summarised; CER gate is ours |

Owner: Rashed Atieh. Last reviewed: 2026-10-11.


Vendored into almamlaka-pdf-assistant from Rashed Atieh's arabic-rag-pipeline toolkit on 2026-10-15. Standard library only. Update by re-copying from the plugin, not by local edits.
