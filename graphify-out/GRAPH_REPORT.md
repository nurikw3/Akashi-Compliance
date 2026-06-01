# Graph Report - AkashiCompliance  (2026-06-02)

## Corpus Check
- 163 files · ~67,873 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1163 nodes · 1915 edges · 51 communities detected
- Extraction: 84% EXTRACTED · 16% INFERRED · 0% AMBIGUOUS · INFERRED: 306 edges (avg confidence: 0.79)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `a80c000f`
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
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 77|Community 77]]

## God Nodes (most connected - your core abstractions)
1. `cn()` - 55 edges
2. `str` - 51 edges
3. `process_case()` - 37 edges
4. `map_info_data()` - 29 edges
5. `AdataProvider` - 28 edges
6. `build_affiliate_tree()` - 21 edges
7. `_build_full_context()` - 20 edges
8. `get_connection()` - 18 edges
9. `get_case()` - 18 edges
10. `CompanyData` - 16 edges

## Surprising Connections (you probably didn't know these)
- `test_tax_risk_does_not_set_sanctions_list()` --calls--> `map_info_data()`  [INFERRED]
  tests/test_risk_scoring.py → app/services/adata/info_mapper.py
- `test_normalize_adata_base_url_appends_company_after_api()` --calls--> `normalize_adata_base_url()`  [INFERRED]
  tests/test_config.py → app/core/config.py
- `test_normalize_adata_base_url_keeps_full_company_path()` --calls--> `normalize_adata_base_url()`  [INFERRED]
  tests/test_config.py → app/core/config.py
- `test_normalize_adata_base_url_from_host_only()` --calls--> `normalize_adata_base_url()`  [INFERRED]
  tests/test_config.py → app/core/config.py
- `save_audit()` --calls--> `RuntimeError`  [INFERRED]
  backend/database.py → app/legacy/adata.py

## Communities (90 total, 13 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (35): ABC, deep_find(), info_has(), Return the first non-empty value for any key in ``keys`` (case-insensitive)., Return the first non-empty value for any key in ``keys`` (case-insensitive)., Return the first non-empty value for any key in ``keys`` (case-insensitive)., lifespan(), BaseProvider (+27 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (70): AdataError, _check_url(), download_company_report(), _fallbacks_for_info(), fetch_beneficiary(), fetch_company_info(), _fetch_fallback(), fetch_non_resident_affiliations() (+62 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (59): normalize_person_name(), Return a displayable person name; ignore nested risk/JSON blobs., case_to_api(), Fix legacy rows where ``director`` was stored as str(riskFactor.head) blob., _repair_stale_director(), check_upload_duplicates(), download_case_report(), generate_case_full_report() (+51 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (58): _collect_bool_flags(), _collect_risk_flags(), _collect_status_flags(), _founders_from_block(), _has_critical_risk(), info_has_structured_blocks(), _litigation_block(), _litigation_totals() (+50 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (49): AdataError, download_company_report(), _fetch(), _poll(), run_parallel_checks(), build_lseg_section(), _decode_sources(), _extract_hits() (+41 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (49): _build_full_context(), _collect_affiliate_enrichments(), _format_affiliate_analysis(), _format_affiliate_tree_compact(), _format_court_case_line(), _format_director_companies(), _format_lseg_extended_block(), _format_lseg_extended_entity() (+41 more)

### Community 6 - "Community 6"
Cohesion: 0.1
Nodes (36): AdataError, download_company_report(), Raised when the Adata workflow fails or returns unusable data., _request_job(), run_parallel_checks(), _safe_json(), download_audit_pdf(), get_audit() (+28 more)

### Community 7 - "Community 7"
Cohesion: 0.08
Nodes (42): chat_reply_for_case(), generate_conclusion_for_case(), AI jobs run in TaskIQ worker or inline fallback., health(), enqueue_affiliate_tree(), enqueue_ai_conclusion(), enqueue_case_pipeline(), enqueue_chat_reply() (+34 more)

### Community 8 - "Community 8"
Cohesion: 0.07
Nodes (30): AuditDetail, AuditHistoryItem, AuditRunRequest, strip_string(), BaseModel, build_audit_hash(), _build_pdf_path(), _collect_boolean_flags() (+22 more)

### Community 9 - "Community 9"
Cohesion: 0.1
Nodes (33): rebuild_case_graph(), _affiliates_from_company_data(), _apply_has_report_flags(), build_affiliate_tree(), cache_snapshot(), _count_nodes(), _display_company_name(), _empty_tree_meta() (+25 more)

### Community 10 - "Community 10"
Cohesion: 0.14
Nodes (30): parse_bins_upload(), parse_upload_file(), _digits_only(), _find_column_index(), _header_matches(), _looks_like_header_row(), _name_from_freeform_line(), _normalize_header() (+22 more)

### Community 12 - "Community 12"
Cohesion: 0.11
Nodes (17): _build_hmac_headers(), _hmac_signature(), LsegClient, LSEG World-Check One v3 HTTP client.  Supports two authentication modes: - HMAC, True when HMAC mode should be used (api-key + api-secret configured)., Obtain/cache OAuth2 Bearer token (only used in non-HMAC mode)., Execute an authenticated request using HMAC or OAuth., Create a WC1 case and screen it synchronously. Returns full case object. (+9 more)

### Community 13 - "Community 13"
Cohesion: 0.19
Nodes (23): add_chat_message(), add_document(), create_case(), _deserialize_audit(), _deserialize_case(), ensure_storage(), find_case_by_iin(), get_audit_by_hash() (+15 more)

### Community 14 - "Community 14"
Cohesion: 0.16
Nodes (13): _adata_sanction_flags(), _lseg_requires_high_risk(), MetricResult, Unified risk scoring engine.  Produces a 0–100 score from 7 weighted metrics sou, Calculate risk score from enriched_data (Adata) + optional lseg section., Calculate risk score from enriched_data (Adata) + optional lseg section., RiskScorer, ScoringResult (+5 more)

### Community 15 - "Community 15"
Cohesion: 0.1
Nodes (8): Sheet(), SheetDescription(), SheetHeader(), SheetTitle(), SidebarMenuButton(), useSidebar(), Skeleton(), TooltipContent()

### Community 16 - "Community 16"
Cohesion: 0.12
Nodes (14): collectAllSanctionLists(), collectEntitySanctionLists(), computeSanctionSummaryStats(), groupSanctionsByJurisdiction(), handleDownloadReport(), JurisdictionSanctionGroups(), src(), uniqueSanctionListLabels() (+6 more)

### Community 17 - "Community 17"
Cohesion: 0.14
Nodes (11): build_case_context(), build_short_context(), context_as_json_snippet(), _lines(), Build a structured text dossier for the compliance AI assistant., Trim very long context for token limits., Minimal surface context — LLM uses tools for details., Trim very long context for token limits. (+3 more)

### Community 18 - "Community 18"
Cohesion: 0.13
Nodes (13): applyCollapse(), buildNodeMeta(), countDescendants(), countHiddenNodes(), formatRoleLabel(), handleClick(), handleOpenCase(), isCompanyBin() (+5 more)

### Community 20 - "Community 20"
Cohesion: 0.19
Nodes (10): run(), fetchAiStatus(), fetchCase(), fetchCaseScore(), fetchNodeReport(), lookupCompany(), parseCase(), rebuildAffiliateTree() (+2 more)

### Community 21 - "Community 21"
Cohesion: 0.34
Nodes (14): get_basic(), get_pdf_report(), get_relation(), get_riskfactor(), get_sanctions(), log(), main(), poll() (+6 more)

### Community 22 - "Community 22"
Cohesion: 0.21
Nodes (11): _affiliate_profile_summary(), _company_data_from_info(), _extract_director_iin(), _fetch_enrichment_profile(), _names_match(), _normalize_iin(), Fetch Adata /info for *iin* and return normalized enrichment dict., Fetch Adata /info for *iin* and return normalized enrichment dict. (+3 more)

### Community 23 - "Community 23"
Cohesion: 0.2
Nodes (11): is_placeholder_company_name(), resolve_company_display_name(), process_case(), Adata enrichment only; AI conclusion is queued separately., Adata enrichment + LSEG screening + unified scoring. AI conclusion queued separa, Adata enrichment + LSEG screening + unified scoring. AI conclusion queued separa, Adata enrichment + LSEG screening + unified scoring. AI conclusion queued separa, Adata enrichment + LSEG screening + unified scoring. AI conclusion queued separa (+3 more)

### Community 24 - "Community 24"
Cohesion: 0.3
Nodes (8): buildCaseGroups(), caseScore(), collectBinsFromTree(), dedupeCasesByBin(), normalizeBin(), pickCanonicalCaseForBin(), pickPrimary(), UnionFind

### Community 25 - "Community 25"
Cohesion: 0.36
Nodes (10): _deserialize_row(), ensure_storage(), get_audit_by_hash(), get_audit_by_id(), get_connection(), init_db(), list_audits(), Legacy Streamlit audit helpers — backed by the shared PostgreSQL database. (+2 more)

### Community 26 - "Community 26"
Cohesion: 0.2
Nodes (10): _build_lseg_extended_targets(), _collect_nonresident_nodes_from_tree(), Walk the affiliate tree and collect all nodes without a valid KZ BIN., Walk the affiliate tree and collect all nodes without a valid KZ BIN., Walk the affiliate tree and collect all nodes without a valid KZ BIN., Collect non-resident LSEG targets from enrichment, Adata extras, and affiliate t, Collect non-resident LSEG targets from enrichment, Adata extras, and affiliate t, Collect non-resident LSEG targets from enrichment, Adata extras, and affiliate t (+2 more)

### Community 27 - "Community 27"
Cohesion: 0.31
Nodes (9): _apply_courts_from_data(), build_assessment(), build_graph(), company_data_to_enrichment(), empty_enrichment(), _is_adata_section(), Neutral empty shell — no seeded fake court/affiliate rows., _sanction_related_flag_labels() (+1 more)

### Community 28 - "Community 28"
Cohesion: 0.24
Nodes (5): Header(), CasesProvider(), generateMockAssessment(), generateMockEnrichment(), seededRandom()

### Community 30 - "Community 30"
Cohesion: 0.29
Nodes (6): checkUploadDuplicates(), parseBinsLocally(), parseBinsText(), parseImportFile(), AlertDialog(), AlertDialogDescription()

### Community 31 - "Community 31"
Cohesion: 0.22
Nodes (5): LoadingGif(), FullReportPage(), fetchFullReport(), generateFullReport(), useCases()

### Community 34 - "Community 34"
Cohesion: 0.32
Nodes (6): normalize_adata_base_url(), Ensure company API prefix; fix common ``/api`` without ``/company`` typo., Settings, test_normalize_adata_base_url_appends_company_after_api(), test_normalize_adata_base_url_from_host_only(), test_normalize_adata_base_url_keeps_full_company_path()

### Community 35 - "Community 35"
Cohesion: 0.25
Nodes (8): build_lseg_extended_entities(), Map screen_batch raw results to the shape expected by the frontend., Map screen_batch raw results to the shape expected by the frontend., Screen targets via LSEG batch and return lsegExtended dict., Screen targets via LSEG batch and return lsegExtended dict., Screen targets via LSEG batch and return lsegExtended dict., Screen targets via LSEG batch and return lsegExtended dict., _run_lseg_extended_screening()

### Community 36 - "Community 36"
Cohesion: 0.25
Nodes (8): Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, rescreen_case_lseg()

### Community 38 - "Community 38"
Cohesion: 0.48
Nodes (5): addToRemoveQueue(), dispatch(), genId(), reducer(), toast()

### Community 42 - "Community 42"
Cohesion: 0.53
Nodes (5): _deep_search(), _render_history(), _request(), _show_audit(), _show_status()

### Community 43 - "Community 43"
Cohesion: 0.4
Nodes (4): risk_from_company_data(), Enum, RiskLevel, RiskService

### Community 45 - "Community 45"
Cohesion: 0.4
Nodes (5): Re-run LSEG batch screening for all non-resident targets including affiliate tre, Re-run LSEG batch screening for all non-resident targets including affiliate tre, Re-run LSEG batch screening for all non-resident targets including affiliate tre, Re-run LSEG batch screening for all non-resident targets including affiliate tre, rescreen_lseg_extended()

### Community 57 - "Community 57"
Cohesion: 0.67
Nodes (3): _ensure_test_database(), Isolate tests from developer PostgreSQL data., _test_database_url()

### Community 58 - "Community 58"
Cohesion: 0.83
Nodes (3): _copy_table(), migrate(), _sqlite_path()

## Knowledge Gaps
- **261 isolated node(s):** `Compatibility shim for legacy imports.`, `Settings`, `Ensure company API prefix; fix common ``/api`` without ``/company`` typo.`, `Legacy Streamlit audit helpers — backed by the shared PostgreSQL database.`, `Search cases by company name using ILIKE.` (+256 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `str` connect `Community 3` to `Community 0`, `Community 1`, `Community 2`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 9`, `Community 10`, `Community 12`, `Community 13`, `Community 21`, `Community 22`, `Community 23`, `Community 25`, `Community 26`, `Community 27`, `Community 43`?**
  _High betweenness centrality (0.275) - this node is a cross-community bridge._
- **Why does `process_case()` connect `Community 23` to `Community 0`, `Community 1`, `Community 2`, `Community 35`, `Community 3`, `Community 7`, `Community 9`, `Community 43`, `Community 17`, `Community 22`, `Community 26`, `Community 27`?**
  _High betweenness centrality (0.108) - this node is a cross-community bridge._
- **Why does `CompanyData` connect `Community 0` to `Community 8`, `Community 43`, `Community 22`, `Community 14`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Are the 50 inferred relationships involving `str` (e.g. with `save_audit()` and `update_pdf_path()`) actually correct?**
  _`str` has 50 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `process_case()` (e.g. with `lookup_company()` and `case_pipeline_task()`) actually correct?**
  _`process_case()` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `map_info_data()` (e.g. with `_company_data_from_info()` and `str`) actually correct?**
  _`map_info_data()` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `AdataProvider` (e.g. with `lifespan()` and `_ensure_worker_context()`) actually correct?**
  _`AdataProvider` has 12 INFERRED edges - model-reasoned connections that need verification._