# Graph Report - AkashiCompliance  (2026-05-28)

## Corpus Check
- 143 files · ~45,657 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 787 nodes · 1298 edges · 36 communities detected
- Extraction: 84% EXTRACTED · 16% INFERRED · 0% AMBIGUOUS · INFERRED: 211 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 66|Community 66]]

## God Nodes (most connected - your core abstractions)
1. `cn()` - 53 edges
2. `str` - 35 edges
3. `AdataProvider` - 28 edges
4. `map_info_data()` - 22 edges
5. `build_affiliate_tree()` - 18 edges
6. `get_connection()` - 17 edges
7. `enqueue_case_pipeline()` - 15 edges
8. `process_case()` - 15 edges
9. `BaseModel` - 13 edges
10. `get_case()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `test_map_core_info_structure()` --calls--> `map_info_data()`  [INFERRED]
  tests/test_adata_info_mapper.py → app/services/adata/info_mapper.py
- `test_normalize_adata_base_url_appends_company_after_api()` --calls--> `normalize_adata_base_url()`  [INFERRED]
  tests/test_config.py → app/core/config.py
- `test_normalize_adata_base_url_keeps_full_company_path()` --calls--> `normalize_adata_base_url()`  [INFERRED]
  tests/test_config.py → app/core/config.py
- `test_normalize_adata_base_url_from_host_only()` --calls--> `normalize_adata_base_url()`  [INFERRED]
  tests/test_config.py → app/core/config.py
- `save_audit()` --calls--> `RuntimeError`  [INFERRED]
  backend/database.py → app/legacy/adata.py

## Communities (77 total, 14 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (30): ABC, deep_find(), info_has(), Return the first non-empty value for any key in ``keys`` (case-insensitive)., Return the first non-empty value for any key in ``keys`` (case-insensitive)., lifespan(), BaseProvider, BaseProvider (+22 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (46): case_to_api(), check_upload_duplicates(), download_case_report(), get_case(), get_case_graph(), get_conclusion(), get_node_report(), _import_upload_item() (+38 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (21): handleOpenCase(), isCompanyBin(), run(), handleDownloadReport(), src(), caseReportPdfUrl(), checkUploadDuplicates(), downloadCaseReport() (+13 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (24): build_case_context(), context_as_json_snippet(), _lines(), Build a structured text dossier for the compliance AI assistant., Trim very long context for token limits., Human-readable dossier for LLM and template replies., chat_reply_for_case(), generate_conclusion_for_case() (+16 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (31): rebuild_case_graph(), _affiliates_from_company_data(), _apply_has_report_flags(), build_affiliate_tree(), cache_snapshot(), _count_nodes(), _empty_tree_meta(), get_cached_node_report() (+23 more)

### Community 5 - "Community 5"
Cohesion: 0.1
Nodes (31): _collect_bool_flags(), _collect_risk_flags(), _collect_status_flags(), _founders_from_block(), _has_critical_risk(), _litigation_block(), _litigation_totals(), map_info_data() (+23 more)

### Community 6 - "Community 6"
Cohesion: 0.13
Nodes (30): AdataError, _check_url(), download_company_report(), _fallbacks_for_info(), fetch_company_info(), _fetch_fallback(), get_basic(), get_courtcase() (+22 more)

### Community 7 - "Community 7"
Cohesion: 0.11
Nodes (15): AuditDetail, AuditHistoryItem, AuditRunRequest, strip_string(), BaseModel, AuditDetail, AuditHistoryItem, AuditRunRequest (+7 more)

### Community 9 - "Community 9"
Cohesion: 0.17
Nodes (22): download_audit_pdf(), get_audit(), get_history(), healthcheck(), lifespan(), run_audit(), _deserialize_row(), ensure_storage() (+14 more)

### Community 10 - "Community 10"
Cohesion: 0.2
Nodes (22): parse_upload_file(), _digits_only(), _find_column_index(), _header_matches(), _looks_like_header_row(), _name_from_freeform_line(), _normalize_header(), _paragraph_lines() (+14 more)

### Community 11 - "Community 11"
Cohesion: 0.1
Nodes (8): Sheet(), SheetDescription(), SheetHeader(), SheetTitle(), SidebarMenuButton(), useSidebar(), Skeleton(), TooltipContent()

### Community 12 - "Community 12"
Cohesion: 0.13
Nodes (15): ProviderRegistry, build_audit_hash(), _build_pdf_path(), _collect_boolean_flags(), ensure_pdf_for_audit(), resolve_status(), run_or_load_audit(), to_audit_detail() (+7 more)

### Community 13 - "Community 13"
Cohesion: 0.21
Nodes (21): add_chat_message(), add_document(), create_case(), _deserialize_audit(), _deserialize_case(), ensure_storage(), find_case_by_iin(), get_audit_by_hash() (+13 more)

### Community 14 - "Community 14"
Cohesion: 0.13
Nodes (17): _apply_courts_from_data(), build_assessment(), build_graph(), company_data_to_enrichment(), empty_enrichment(), _is_adata_section(), Neutral empty shell — no seeded fake court/affiliate rows., risk_from_company_data() (+9 more)

### Community 15 - "Community 15"
Cohesion: 0.2
Nodes (14): AdataError, download_company_report(), Raised when the Adata workflow fails or returns unusable data., _request_job(), run_parallel_checks(), _safe_json(), build_audit_hash(), _build_pdf_path() (+6 more)

### Community 16 - "Community 16"
Cohesion: 0.24
Nodes (15): AdataError, download_company_report(), _fetch(), _poll(), run_parallel_checks(), _deserialize_row(), ensure_storage(), get_audit_by_hash() (+7 more)

### Community 17 - "Community 17"
Cohesion: 0.34
Nodes (14): get_basic(), get_pdf_report(), get_relation(), get_riskfactor(), get_sanctions(), log(), main(), poll() (+6 more)

### Community 18 - "Community 18"
Cohesion: 0.3
Nodes (8): buildCaseGroups(), caseScore(), collectBinsFromTree(), dedupeCasesByBin(), normalizeBin(), pickCanonicalCaseForBin(), pickPrimary(), UnionFind

### Community 19 - "Community 19"
Cohesion: 0.24
Nodes (5): Header(), CasesProvider(), generateMockAssessment(), generateMockEnrichment(), seededRandom()

### Community 25 - "Community 25"
Cohesion: 0.32
Nodes (6): normalize_adata_base_url(), Ensure company API prefix; fix common ``/api`` without ``/company`` typo., Settings, test_normalize_adata_base_url_appends_company_after_api(), test_normalize_adata_base_url_from_host_only(), test_normalize_adata_base_url_keeps_full_company_path()

### Community 26 - "Community 26"
Cohesion: 0.48
Nodes (5): addToRemoveQueue(), dispatch(), genId(), reducer(), toast()

### Community 30 - "Community 30"
Cohesion: 0.53
Nodes (5): _deep_search(), _render_history(), _request(), _show_audit(), _show_status()

## Knowledge Gaps
- **74 isolated node(s):** `Compatibility shim for legacy imports.`, `Settings`, `Ensure company API prefix; fix common ``/api`` without ``/company`` typo.`, `Returns (action, api_case, job_or_none). action: created | skipped | refreshed.`, `Heavy jobs executed in TaskIQ worker process(es).` (+69 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `str` connect `Community 5` to `Community 0`, `Community 1`, `Community 4`, `Community 6`, `Community 9`, `Community 10`, `Community 12`, `Community 13`, `Community 14`, `Community 16`, `Community 17`?**
  _High betweenness centrality (0.204) - this node is a cross-community bridge._
- **Why does `cn()` connect `Community 8` to `Community 2`, `Community 11`, `Community 20`, `Community 21`, `Community 22`, `Community 23`, `Community 24`, `Community 27`, `Community 28`, `Community 31`, `Community 32`, `Community 33`, `Community 34`, `Community 35`, `Community 36`, `Community 37`, `Community 38`, `Community 39`, `Community 40`, `Community 41`, `Community 45`, `Community 46`, `Community 47`, `Community 48`, `Community 49`, `Community 50`, `Community 51`, `Community 52`?**
  _High betweenness centrality (0.093) - this node is a cross-community bridge._
- **Why does `CompanyData` connect `Community 0` to `Community 14`, `Community 7`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Are the 34 inferred relationships involving `str` (e.g. with `save_audit()` and `update_pdf_path()`) actually correct?**
  _`str` has 34 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `AdataProvider` (e.g. with `lifespan()` and `_ensure_worker_context()`) actually correct?**
  _`AdataProvider` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `map_info_data()` (e.g. with `str` and `._map_raw()`) actually correct?**
  _`map_info_data()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `build_affiliate_tree()` (e.g. with `affiliate_tree_task()` and `_run_tree_inline()`) actually correct?**
  _`build_affiliate_tree()` has 7 INFERRED edges - model-reasoned connections that need verification._