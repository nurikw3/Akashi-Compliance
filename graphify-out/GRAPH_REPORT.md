# Graph Report - AkashiCompliance  (2026-06-01)

## Corpus Check
- 151 files · ~52,737 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 867 nodes · 1417 edges · 39 communities detected
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 218 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `8d1e1e37`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

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
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 66|Community 66]]

## God Nodes (most connected - your core abstractions)
1. `cn()` - 53 edges
2. `str` - 37 edges
3. `AdataProvider` - 28 edges
4. `map_info_data()` - 22 edges
5. `build_affiliate_tree()` - 18 edges
6. `get_connection()` - 17 edges
7. `process_case()` - 17 edges
8. `enqueue_case_pipeline()` - 15 edges
9. `get_case()` - 14 edges
10. `BaseModel` - 13 edges

## Surprising Connections (you probably didn't know these)
- `test_normalize_adata_base_url_appends_company_after_api()` --calls--> `normalize_adata_base_url()`  [INFERRED]
  tests/test_config.py → app/core/config.py
- `test_normalize_adata_base_url_keeps_full_company_path()` --calls--> `normalize_adata_base_url()`  [INFERRED]
  tests/test_config.py → app/core/config.py
- `test_normalize_adata_base_url_from_host_only()` --calls--> `normalize_adata_base_url()`  [INFERRED]
  tests/test_config.py → app/core/config.py
- `save_audit()` --calls--> `RuntimeError`  [INFERRED]
  backend/database.py → app/legacy/adata.py
- `_lookup_resolve_from_parent_cache()` --calls--> `case_to_api()`  [INFERRED]
  tests/test_lookup.py → app/models/serializers.py

## Communities (79 total, 13 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (31): ABC, deep_find(), info_has(), Return the first non-empty value for any key in ``keys`` (case-insensitive)., Return the first non-empty value for any key in ``keys`` (case-insensitive)., lifespan(), BaseProvider, BaseProvider (+23 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (55): _collect_bool_flags(), _collect_risk_flags(), _collect_status_flags(), _founders_from_block(), _has_critical_risk(), _litigation_block(), _litigation_totals(), map_info_data() (+47 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (24): handleOpenCase(), isCompanyBin(), run(), handleDownloadReport(), src(), handleRescreen(), caseReportPdfUrl(), checkUploadDuplicates() (+16 more)

### Community 3 - "Community 3"
Cohesion: 0.1
Nodes (36): AdataError, download_company_report(), Raised when the Adata workflow fails or returns unusable data., _request_job(), run_parallel_checks(), _safe_json(), download_audit_pdf(), get_audit() (+28 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (40): chat_reply_for_case(), generate_conclusion_for_case(), AI jobs run in TaskIQ worker or inline fallback., health(), enqueue_affiliate_tree(), enqueue_ai_conclusion(), enqueue_case_pipeline(), enqueue_chat_reply() (+32 more)

### Community 5 - "Community 5"
Cohesion: 0.1
Nodes (32): rebuild_case_graph(), _affiliates_from_company_data(), _apply_has_report_flags(), build_affiliate_tree(), cache_snapshot(), _count_nodes(), _empty_tree_meta(), get_cached_node_report() (+24 more)

### Community 6 - "Community 6"
Cohesion: 0.13
Nodes (30): AdataError, _check_url(), download_company_report(), _fallbacks_for_info(), fetch_company_info(), _fetch_fallback(), get_basic(), get_courtcase() (+22 more)

### Community 7 - "Community 7"
Cohesion: 0.12
Nodes (25): case_to_api(), check_upload_duplicates(), download_case_report(), get_case(), get_case_graph(), get_case_score(), get_conclusion(), get_node_report() (+17 more)

### Community 9 - "Community 9"
Cohesion: 0.11
Nodes (15): AuditDetail, AuditHistoryItem, AuditRunRequest, strip_string(), BaseModel, AuditDetail, AuditHistoryItem, AuditRunRequest (+7 more)

### Community 10 - "Community 10"
Cohesion: 0.2
Nodes (22): parse_upload_file(), _digits_only(), _find_column_index(), _header_matches(), _looks_like_header_row(), _name_from_freeform_line(), _normalize_header(), _paragraph_lines() (+14 more)

### Community 11 - "Community 11"
Cohesion: 0.1
Nodes (8): Sheet(), SheetDescription(), SheetHeader(), SheetTitle(), SidebarMenuButton(), useSidebar(), Skeleton(), TooltipContent()

### Community 12 - "Community 12"
Cohesion: 0.13
Nodes (14): _build_hmac_headers(), _hmac_signature(), LsegClient, LSEG World-Check One v3 HTTP client.  Supports two authentication modes: - HMAC, True when HMAC mode should be used (api-key + api-secret configured)., Obtain/cache OAuth2 Bearer token (only used in non-HMAC mode)., Execute an authenticated request using HMAC or OAuth., Create a WC1 case and screen it synchronously. Returns full case object. (+6 more)

### Community 13 - "Community 13"
Cohesion: 0.13
Nodes (15): ProviderRegistry, build_audit_hash(), _build_pdf_path(), _collect_boolean_flags(), ensure_pdf_for_audit(), resolve_status(), run_or_load_audit(), to_audit_detail() (+7 more)

### Community 14 - "Community 14"
Cohesion: 0.21
Nodes (21): add_chat_message(), add_document(), create_case(), _deserialize_audit(), _deserialize_case(), ensure_storage(), find_case_by_iin(), get_audit_by_hash() (+13 more)

### Community 15 - "Community 15"
Cohesion: 0.17
Nodes (8): build_case_context(), context_as_json_snippet(), _lines(), Build a structured text dossier for the compliance AI assistant., Trim very long context for token limits., Human-readable dossier for LLM and template replies., AIService, test_build_case_context_includes_sections()

### Community 16 - "Community 16"
Cohesion: 0.22
Nodes (16): AdataError, download_company_report(), _fetch(), _poll(), run_parallel_checks(), _deserialize_row(), ensure_storage(), get_audit_by_hash() (+8 more)

### Community 17 - "Community 17"
Cohesion: 0.34
Nodes (14): get_basic(), get_pdf_report(), get_relation(), get_riskfactor(), get_sanctions(), log(), main(), poll() (+6 more)

### Community 18 - "Community 18"
Cohesion: 0.17
Nodes (13): build_lseg_section(), _extract_hits(), _extract_media(), Map LSEG World-Check One v3 API responses to internal dicts., Parse /cases/{id}/results response into a flat list of hits., Parse /media-check/results response into a compact list of articles., Assemble the enriched_data.lseg section stored in the DB., is_available() (+5 more)

### Community 19 - "Community 19"
Cohesion: 0.28
Nodes (5): MetricResult, Unified risk scoring engine.  Produces a 0–100 score from 7 weighted metrics sou, Calculate risk score from enriched_data (Adata) + optional lseg section., RiskScorer, ScoringResult

### Community 20 - "Community 20"
Cohesion: 0.3
Nodes (8): buildCaseGroups(), caseScore(), collectBinsFromTree(), dedupeCasesByBin(), normalizeBin(), pickCanonicalCaseForBin(), pickPrimary(), UnionFind

### Community 21 - "Community 21"
Cohesion: 0.24
Nodes (5): Header(), CasesProvider(), generateMockAssessment(), generateMockEnrichment(), seededRandom()

### Community 27 - "Community 27"
Cohesion: 0.32
Nodes (6): normalize_adata_base_url(), Ensure company API prefix; fix common ``/api`` without ``/company`` typo., Settings, test_normalize_adata_base_url_appends_company_after_api(), test_normalize_adata_base_url_from_host_only(), test_normalize_adata_base_url_keeps_full_company_path()

### Community 28 - "Community 28"
Cohesion: 0.48
Nodes (5): addToRemoveQueue(), dispatch(), genId(), reducer(), toast()

### Community 32 - "Community 32"
Cohesion: 0.53
Nodes (5): _deep_search(), _render_history(), _request(), _show_audit(), _show_status()

### Community 45 - "Community 45"
Cohesion: 0.67
Nodes (3): _ensure_test_database(), Isolate tests from developer PostgreSQL data., _test_database_url()

### Community 46 - "Community 46"
Cohesion: 0.83
Nodes (3): _copy_table(), migrate(), _sqlite_path()

## Knowledge Gaps
- **100 isolated node(s):** `Compatibility shim for legacy imports.`, `Settings`, `Ensure company API prefix; fix common ``/api`` without ``/company`` typo.`, `Legacy Streamlit audit helpers — backed by the shared PostgreSQL database.`, `Returns (action, api_case, job_or_none). action: created | skipped | refreshed.` (+95 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `str` connect `Community 1` to `Community 0`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 10`, `Community 12`, `Community 13`, `Community 14`, `Community 16`, `Community 17`?**
  _High betweenness centrality (0.207) - this node is a cross-community bridge._
- **Why does `cn()` connect `Community 8` to `Community 2`, `Community 11`, `Community 22`, `Community 23`, `Community 24`, `Community 25`, `Community 26`, `Community 29`, `Community 30`, `Community 33`, `Community 34`, `Community 35`, `Community 36`, `Community 38`, `Community 39`, `Community 40`, `Community 41`, `Community 42`, `Community 43`, `Community 44`, `Community 49`, `Community 50`, `Community 51`, `Community 52`, `Community 53`, `Community 54`, `Community 55`?**
  _High betweenness centrality (0.080) - this node is a cross-community bridge._
- **Why does `process_case()` connect `Community 1` to `Community 0`, `Community 4`, `Community 5`, `Community 7`, `Community 15`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 36 inferred relationships involving `str` (e.g. with `save_audit()` and `update_pdf_path()`) actually correct?**
  _`str` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `AdataProvider` (e.g. with `lifespan()` and `_ensure_worker_context()`) actually correct?**
  _`AdataProvider` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `map_info_data()` (e.g. with `str` and `._map_raw()`) actually correct?**
  _`map_info_data()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `build_affiliate_tree()` (e.g. with `affiliate_tree_task()` and `_run_tree_inline()`) actually correct?**
  _`build_affiliate_tree()` has 7 INFERRED edges - model-reasoned connections that need verification._