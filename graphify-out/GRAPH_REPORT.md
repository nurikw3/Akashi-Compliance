# Graph Report - AkashiCompliance  (2026-06-03)

## Corpus Check
- 175 files · ~80,957 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1465 nodes · 2426 edges · 88 communities detected
- Extraction: 84% EXTRACTED · 16% INFERRED · 0% AMBIGUOUS · INFERRED: 394 edges (avg confidence: 0.79)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e303229f`
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
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]
- [[_COMMUNITY_Community 94|Community 94]]
- [[_COMMUNITY_Community 95|Community 95]]
- [[_COMMUNITY_Community 96|Community 96]]
- [[_COMMUNITY_Community 97|Community 97]]
- [[_COMMUNITY_Community 106|Community 106]]
- [[_COMMUNITY_Community 107|Community 107]]
- [[_COMMUNITY_Community 108|Community 108]]
- [[_COMMUNITY_Community 114|Community 114]]

## God Nodes (most connected - your core abstractions)
1. `str` - 73 edges
2. `cn()` - 56 edges
3. `process_case()` - 42 edges
4. `map_info_data()` - 39 edges
5. `AdataProvider` - 30 edges
6. `_build_full_context()` - 27 edges
7. `generate_full_report()` - 26 edges
8. `_build_section_context()` - 22 edges
9. `_template_full_report()` - 22 edges
10. `build_affiliate_tree()` - 21 edges

## Surprising Connections (you probably didn't know these)
- `test_normalize_individual_court_case_case_level_documents()` --calls--> `_normalize_individual_court_case()`  [INFERRED]
  tests/test_adata_individual_courts.py → app/services/adata/client.py
- `test_map_info_data_sets_company_court_cases_on_raw()` --calls--> `map_info_data()`  [INFERRED]
  tests/test_adata_company_detailed_courts.py → app/services/adata/info_mapper.py
- `test_tax_risk_does_not_set_sanctions_list()` --calls--> `map_info_data()`  [INFERRED]
  tests/test_risk_scoring.py → app/services/adata/info_mapper.py
- `test_map_raw_from_info_payload()` --calls--> `AdataProvider`  [INFERRED]
  tests/test_adata_info.py → app/services/enrichment/providers/adata.py
- `test_parse_courtcase_maps_totals_and_years()` --calls--> `AdataProvider`  [INFERRED]
  tests/test_adata_courtcase.py → app/services/enrichment/providers/adata.py

## Communities (127 total, 15 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (63): _apply_bin_courtcase_from_raw(), _collect_bool_flags(), _collect_risk_flags(), _collect_status_flags(), _courtcase_data_from_raw(), _extract_detailed_company_court_cases(), _founders_from_block(), _has_critical_risk() (+55 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (40): AdataError, download_company_report(), Raised when the Adata workflow fails or returns unusable data., _request_job(), run_parallel_checks(), _safe_json(), download_audit_pdf(), get_audit() (+32 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (28): build_case_context(), build_short_context(), context_as_json_snippet(), _lines(), Build a structured text dossier for the compliance AI assistant., Trim very long context for token limits., Minimal surface context — LLM uses tools for details., Trim very long context for token limits. (+20 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (26): BaseModel, build_audit_hash(), _build_pdf_path(), _collect_boolean_flags(), ensure_pdf_for_audit(), resolve_status(), run_or_load_audit(), to_audit_detail() (+18 more)

### Community 4 - "Community 4"
Cohesion: 0.1
Nodes (33): rebuild_case_graph(), _affiliates_from_company_data(), _apply_has_report_flags(), build_affiliate_tree(), cache_snapshot(), _count_nodes(), _display_company_name(), _empty_tree_meta() (+25 more)

### Community 6 - "Community 6"
Cohesion: 0.13
Nodes (31): _build_courts_verdict(), parse_bins_upload(), parse_upload_file(), _digits_only(), _find_column_index(), _header_matches(), _looks_like_header_row(), _name_from_freeform_line() (+23 more)

### Community 7 - "Community 7"
Cohesion: 0.12
Nodes (31): hash_password(), HTTP Basic auth against users stored in PostgreSQL., require_auth(), verify_password(), add_chat_message(), add_document(), create_case(), _deserialize_audit() (+23 more)

### Community 8 - "Community 8"
Cohesion: 0.15
Nodes (25): health(), enqueue_affiliate_tree(), enqueue_ai_conclusion(), enqueue_case_pipeline(), enqueue_chat_reply(), _job_result(), ping_redis(), Enqueue heavy work to TaskIQ (Redis) or run inline when queue is disabled. (+17 more)

### Community 9 - "Community 9"
Cohesion: 0.11
Nodes (17): _build_hmac_headers(), _hmac_signature(), LsegClient, LSEG World-Check One v3 HTTP client.  Supports two authentication modes: - HMAC, True when HMAC mode should be used (api-key + api-secret configured)., Obtain/cache OAuth2 Bearer token (only used in non-HMAC mode)., Execute an authenticated request using HMAC or OAuth., Create a WC1 case and screen it synchronously. Returns full case object. (+9 more)

### Community 10 - "Community 10"
Cohesion: 0.1
Nodes (12): collectAllSanctionLists(), collectEntitySanctionLists(), computeSanctionSummaryStats(), groupSanctionsByJurisdiction(), JurisdictionSanctionGroups(), src(), uniqueSanctionListLabels(), LoadingGif() (+4 more)

### Community 11 - "Community 11"
Cohesion: 0.13
Nodes (16): applyCollapse(), buildNodeMeta(), countDescendants(), countHiddenNodes(), formatRoleLabel(), handleClick(), handleOpenCase(), isCompanyBin() (+8 more)

### Community 12 - "Community 12"
Cohesion: 0.13
Nodes (18): handleDownloadReport(), FullReportPage(), handleGenerate(), caseReportPdfUrl(), downloadCaseReport(), fetchAiStatus(), fetchCase(), fetchCaseScore() (+10 more)

### Community 13 - "Community 13"
Cohesion: 0.09
Nodes (24): fetch_beneficiary(), fetch_non_resident_affiliations(), _poll_with_url(), Like ``_poll`` but accepts an explicit *check_url* instead of the default info/c, Like ``_poll`` but accepts an explicit *check_url* instead of the default info/c, Like ``_poll`` but accepts an explicit *check_url* instead of the default info/c, Return beneficiary list for *iin*, with 12-hour Redis cache., Return beneficiary list for *iin*, with 12-hour Redis cache. (+16 more)

### Community 14 - "Community 14"
Cohesion: 0.12
Nodes (23): _call_llm_section(), _combine_sectional_report(), _format_courts_section(), generate_full_report(), _generate_full_report_impl(), _normalize_section_output(), Generate and save full compliance report. Returns report text., Generate and save full compliance report. Returns report text. (+15 more)

### Community 15 - "Community 15"
Cohesion: 0.09
Nodes (24): _format_lseg_extended_block(), _format_lseg_extended_entity(), _format_lseg_screening_summary(), Format one lsegExtended entry; clean entities get a single line., Human-readable block for all lsegExtended entities., Human-readable block for all lsegExtended entities., Human-readable block for all lsegExtended entities., Format one lsegExtended entry; clean entities get a single line. (+16 more)

### Community 16 - "Community 16"
Cohesion: 0.16
Nodes (13): _adata_sanction_flags(), _lseg_requires_high_risk(), MetricResult, Unified risk scoring engine.  Produces a 0–100 score from 7 weighted metrics sou, Calculate risk score from enriched_data (Adata) + optional lseg section., Calculate risk score from enriched_data (Adata) + optional lseg section., RiskScorer, ScoringResult (+5 more)

### Community 17 - "Community 17"
Cohesion: 0.1
Nodes (8): Sheet(), SheetDescription(), SheetHeader(), SheetTitle(), SidebarMenuButton(), useSidebar(), Skeleton(), TooltipContent()

### Community 18 - "Community 18"
Cohesion: 0.16
Nodes (20): case_to_api(), Fix legacy rows where ``director`` was stored as str(riskFactor.head) blob., _repair_stale_director(), check_upload_duplicates(), download_case_report(), get_case(), get_case_full_report_meta(), get_case_graph() (+12 more)

### Community 19 - "Community 19"
Cohesion: 0.18
Nodes (21): _check_url(), _courtcase_token_path(), _fetch_fallback(), get_basic(), get_courtcase(), _get_endpoint(), get_relation(), get_riskfactor() (+13 more)

### Community 20 - "Community 20"
Cohesion: 0.19
Nodes (5): info_has(), AdataProvider, Prefer nested block inside info, then dedicated fallback key., Prefer nested block inside info, then dedicated fallback key., Prefer nested block inside info, then dedicated fallback key.

### Community 21 - "Community 21"
Cohesion: 0.15
Nodes (14): CompanyData, EnrichmentService, default_section_sources(), _endpoint_ok(), infer_section_sources_from_data(), merge_section_sources(), Infer per-section provider from CompanyData.raw and populated fields., Fallback when only case-level provider list is stored. (+6 more)

### Community 22 - "Community 22"
Cohesion: 0.13
Nodes (15): normalize_adata_base_url(), normalize_adata_courtcase_base_url(), normalize_adata_individual_base_url(), Ensure company API prefix; fix common ``/api`` without ``/company`` typo., Derive Adata company *courtcase* API base from the company base URL., Derive Adata *individual* API base from the company base URL., Settings, test_courtcase_urls_not_under_company_prefix() (+7 more)

### Community 23 - "Community 23"
Cohesion: 0.13
Nodes (18): fetch_company_info(), Start company info job and poll until ``data`` is ready; return that object., Start company info job and poll until ``data`` is ready; return that object., Start company info job and poll until ``data`` is ready; return that object., Start company info job and poll until ``data`` is ready; return that object., Start company info job and poll until ``data`` is ready; return that object., Start company info job and poll until ``data`` is ready; return that object., delete_cached() (+10 more)

### Community 24 - "Community 24"
Cohesion: 0.13
Nodes (18): _fetch_with_cache(), is_available(), _noop(), High-level LSEG World-Check One screening service.  Screens a company (ORGANISAT, Screen company + director via WC1. Returns lseg section dict or None on failure., Screen company + director via WC1. Returns lseg section dict or None on failure., Screen company + director via WC1. Returns lseg section dict or None on failure., Screen multiple entities in parallel with Redis caching and rate limiting. (+10 more)

### Community 25 - "Community 25"
Cohesion: 0.15
Nodes (12): AuthGate(), Header(), checkHealth(), clearAuth(), isAuthenticated(), setAuth(), setAuthToken(), tryAuthFromHash() (+4 more)

### Community 26 - "Community 26"
Cohesion: 0.14
Nodes (17): _decode_sources(), _extract_hits(), _is_material_watchlist_hit(), _primary_name_from_result(), Map LSEG World-Check One v3 API responses to internal dicts., Parse /cases/{id}/results response into a flat list of hits., Return True if any source code contains a known sanctions indicator., Return True if any source code contains a known sanctions indicator. (+9 more)

### Community 27 - "Community 27"
Cohesion: 0.15
Nodes (16): compute_full_report_staleness(), estimate_full_report_context(), full_report_meta_for_row(), _parse_iso(), Freshness and context-size metadata for sectional full reports., True when affiliate tree was rebuilt after the last saved full report., Approximate per-section input size for the sectional LLM pipeline., get_case_full_report() (+8 more)

### Community 28 - "Community 28"
Cohesion: 0.21
Nodes (16): _append_takeaway_block(), _collect_court_rows(), _count_case_source_links(), _extract_case_role_by_parties(), _extract_key_findings(), _infer_risk_tag(), _is_serious_court_category(), _is_unresolved_case() (+8 more)

### Community 29 - "Community 29"
Cohesion: 0.12
Nodes (17): _build_full_context(), _format_affiliate_analysis(), _format_court_case_line(), _format_director_companies(), _is_low_risk_affiliate(), _log_section(), Build compact but complete context for LLM from all case data., Build compact but complete context for LLM from all case data. (+9 more)

### Community 31 - "Community 31"
Cohesion: 0.14
Nodes (16): fetch_individual_court_cases(), _individual_api_base(), _individual_info_check_url(), _individual_token_path(), _normalize_court_documents(), _normalize_individual_court_case(), _poll_individual_court_cases(), Return individual court cases with document links, cached 12h. (+8 more)

### Community 32 - "Community 32"
Cohesion: 0.13
Nodes (16): _build_section_context(), _format_individual_courts_for_llm(), _format_trustworthy_plus_summary(), Format individualCourts dict for LLM context with markdown doc links., Format individualCourts dict for LLM context with markdown doc links., Format individualCourts dict for LLM context with markdown doc links., Format individualCourts dict for LLM context with markdown doc links., Format individualCourts dict for LLM context with markdown doc links. (+8 more)

### Community 33 - "Community 33"
Cohesion: 0.34
Nodes (14): get_basic(), get_pdf_report(), get_relation(), get_riskfactor(), get_sanctions(), log(), main(), poll() (+6 more)

### Community 34 - "Community 34"
Cohesion: 0.14
Nodes (14): _format_individual_court_case(), _is_populated(), _list_data_sources(), List exactly which enriched_data blocks are present and non-empty., List exactly which enriched_data blocks are present and non-empty., Format one individual court case with history and document links., Format one individual court case with history and document links., Format one individual court case with history and document links. (+6 more)

### Community 35 - "Community 35"
Cohesion: 0.16
Nodes (13): is_placeholder_company_name(), resolve_company_display_name(), process_case(), Adata enrichment only; AI conclusion is queued separately., Adata enrichment + LSEG screening + unified scoring. AI conclusion queued separa, Adata enrichment + LSEG screening + unified scoring. AI conclusion queued separa, Adata enrichment + LSEG screening + unified scoring. AI conclusion queued separa, Adata enrichment + LSEG screening + unified scoring. AI conclusion queued separa (+5 more)

### Community 36 - "Community 36"
Cohesion: 0.14
Nodes (14): _build_lseg_extended_targets(), _collect_nonresident_nodes_from_tree(), Walk the affiliate tree and collect all nodes without a valid KZ BIN., Walk the affiliate tree and collect all nodes without a valid KZ BIN., Walk the affiliate tree and collect all nodes without a valid KZ BIN., Collect non-resident LSEG targets from enrichment, Adata extras, and affiliate t, Collect non-resident LSEG targets from enrichment, Adata extras, and affiliate t, Collect non-resident LSEG targets from enrichment, Adata extras, and affiliate t (+6 more)

### Community 37 - "Community 37"
Cohesion: 0.18
Nodes (7): lifespan(), BaseProvider, KompraProvider, Placeholder for future Kompra integration., seeded_random(), stub_enrichment_dict(), StubProvider

### Community 38 - "Community 38"
Cohesion: 0.19
Nodes (12): _court_cases_last_page(), _is_aggregate_court_year_row(), _is_detailed_court_case_row(), _merge_company_info_court_pages(), Yearly litigation summary row (not a single court case)., Single court case with number, parties, documents, or history., Merge paginated ``court_cases`` from company info/check when present., Company detailed court cases from info/check (paginated court_cases). (+4 more)

### Community 39 - "Community 39"
Cohesion: 0.15
Nodes (13): Generate a structured text report without LLM based on case data only., Generate a structured text report without LLM based on case data only., Generate a structured text report without LLM based on case data only., Generate a structured text report without LLM based on case data only., Generate a structured text report without LLM based on case data only., Generate a structured text report without LLM based on case data only., Generate a structured text report without LLM based on case data only., Generate a structured text report without LLM based on case data. (+5 more)

### Community 40 - "Community 40"
Cohesion: 0.23
Nodes (11): _apply_courts_from_data(), build_assessment(), build_graph(), company_data_to_enrichment(), empty_enrichment(), _is_adata_section(), Neutral empty shell — no seeded fake court/affiliate rows., risk_from_company_data() (+3 more)

### Community 41 - "Community 41"
Cohesion: 0.18
Nodes (12): _extract_director_iin_from_basic_payload(), fetch_director_iin(), _normalize_iin_digits(), Extract 12-digit director IIN from basic endpoint or nested basic blocks., Extract 12-digit director IIN from basic endpoint or nested basic blocks., Return director IIN from ``/company/basic/``, cached 24h., Extract 12-digit director IIN from basic endpoint or nested basic blocks., Return director IIN from ``/company/basic/``, cached 24h. (+4 more)

### Community 42 - "Community 42"
Cohesion: 0.18
Nodes (12): AdataError, download_company_report(), fetch_pdf_report_url(), Return Adata PDF download URL (report token + poll info/check for ``data.locatio, Download Adata PDF to *out_path* (uses :func:`fetch_pdf_report_url`)., Return Adata PDF download URL (report token + poll info/check for ``data.locatio, Return Adata PDF download URL (report token + poll info/check for ``data.locatio, Download Adata PDF to *out_path* (uses :func:`fetch_pdf_report_url`). (+4 more)

### Community 43 - "Community 43"
Cohesion: 0.17
Nodes (12): Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, Apply LSEG screening + re-score to an already-enriched case. Returns True on suc, Apply LSEG screening + re-score to an already-enriched case. Returns True on suc (+4 more)

### Community 44 - "Community 44"
Cohesion: 0.24
Nodes (11): _affiliate_profile_summary(), _build_affiliate_profile(), _build_individual_courts_meta(), _extract_director_iin(), _fetch_individual_courts_for_case(), _names_match(), _normalize_iin(), Try to find director IIN from enrichment, relation data, or affiliate tree. (+3 more)

### Community 45 - "Community 45"
Cohesion: 0.17
Nodes (10): _fallbacks_for_info(), Endpoint suffixes to call when ``info`` does not contain enough data., Endpoint suffixes to call when ``info`` does not contain enough data., Endpoint suffixes to call when ``info`` does not contain enough data., Endpoint suffixes to call when ``info`` does not contain enough data., Endpoint suffixes to call when ``info`` does not contain enough data., Endpoint suffixes to call when ``info`` does not contain enough data., Endpoint suffixes to call when ``info`` does not contain enough data. (+2 more)

### Community 46 - "Community 46"
Cohesion: 0.24
Nodes (5): checkUploadDuplicates(), parseImportFile(), useCases(), AlertDialog(), AlertDialogDescription()

### Community 47 - "Community 47"
Cohesion: 0.3
Nodes (8): buildCaseGroups(), caseScore(), collectBinsFromTree(), dedupeCasesByBin(), normalizeBin(), pickCanonicalCaseForBin(), pickPrimary(), UnionFind

### Community 48 - "Community 48"
Cohesion: 0.18
Nodes (11): fetch_relation_extended(), Return extended relation/affiliation data for *iin*, with 12-hour Redis cache., Return extended relation/affiliation data for *iin*, with 12-hour Redis cache., Return extended relation/affiliation data for *iin*, with 12-hour Redis cache., Return extended relation/affiliation data for *iin*, with 12-hour Redis cache., Return extended relation/affiliation data for *iin*, with 12-hour Redis cache., Return extended relation/affiliation data for *iin*, with 12-hour Redis cache., Return extended relation/affiliation data for *iin*, with 12-hour Redis cache. (+3 more)

### Community 49 - "Community 49"
Cohesion: 0.36
Nodes (10): _deserialize_row(), ensure_storage(), get_audit_by_hash(), get_audit_by_id(), get_connection(), init_db(), list_audits(), Legacy Streamlit audit helpers — backed by the shared PostgreSQL database. (+2 more)

### Community 50 - "Community 50"
Cohesion: 0.2
Nodes (3): ABC, BaseProvider, ProviderRegistry

### Community 51 - "Community 51"
Cohesion: 0.2
Nodes (8): build_lseg_section(), Assemble the enriched_data.lseg section stored in the DB., Assemble the enriched_data.lseg section stored in the DB., Assemble the enriched_data.lseg section stored in the DB., Assemble the enriched_data.lseg section stored in the DB., filter_bin_query_false_positive_hits(), Drop obvious token matches caused by screening a BIN string instead of a legal n, test_filter_removes_bin_token_false_positives()

### Community 52 - "Community 52"
Cohesion: 0.24
Nodes (8): _import_upload_item(), Returns (action, api_case, job_or_none). action: created | skipped | refreshed., Returns (action, api_case, job_or_none). action: created | skipped | refreshed., Returns (action, api_case, job_or_none). action: created | skipped | refreshed., Returns (action, api_case, job_or_none). action: created | skipped | refreshed., test_import_create_always_adds_new_row(), test_import_refresh_reuses_case_and_enqueues(), test_import_skip_existing_does_not_create_second_case()

### Community 53 - "Community 53"
Cohesion: 0.2
Nodes (10): Re-run LSEG batch screening for all non-resident targets including affiliate tre, Re-run LSEG batch screening for all non-resident targets including affiliate tre, Re-run LSEG batch screening for all non-resident targets including affiliate tre, Re-run LSEG batch screening for all non-resident targets including affiliate tre, Re-run LSEG batch screening for all non-resident targets including affiliate tre, Re-run LSEG batch screening for all non-resident targets including affiliate tre, Re-run LSEG batch screening for all non-resident targets including affiliate tre, Re-run LSEG batch screening for all non-resident targets including affiliate tre (+2 more)

### Community 54 - "Community 54"
Cohesion: 0.2
Nodes (10): build_lseg_extended_entities(), Map screen_batch raw results to the shape expected by the frontend., Map screen_batch raw results to the shape expected by the frontend., Screen targets via LSEG batch and return lsegExtended dict., Screen targets via LSEG batch and return lsegExtended dict., Screen targets via LSEG batch and return lsegExtended dict., Screen targets via LSEG batch and return lsegExtended dict., Screen targets via LSEG batch and return lsegExtended dict. (+2 more)

### Community 55 - "Community 55"
Cohesion: 0.2
Nodes (10): info_has_structured_blocks(), True when payload matches unified info API (basic + status blocks)., True when payload matches unified info API (basic + status blocks)., True when payload matches unified info API (basic + status blocks)., True when payload matches unified info API (basic + status blocks)., True when payload matches unified info API (basic + status blocks)., True when payload matches unified info API (basic + status blocks)., True when payload matches unified info API (basic + status blocks). (+2 more)

### Community 57 - "Community 57"
Cohesion: 0.22
Nodes (9): fetch_trustworthy_plus(), Return trustworthy-plus compliance data for *iin*, with 12-hour Redis cache., Return trustworthy-plus compliance data for *iin*, with 12-hour Redis cache., Return trustworthy-plus compliance data for *iin*, with 12-hour Redis cache., Return trustworthy-plus compliance data for *iin*, with 12-hour Redis cache., Return trustworthy-plus compliance data for *iin*, with 12-hour Redis cache., Return trustworthy-plus compliance data for *iin*, with 12-hour Redis cache., Return trustworthy-plus compliance data for *iin*, with 12-hour Redis cache. (+1 more)

### Community 58 - "Community 58"
Cohesion: 0.22
Nodes (9): _fetch_with_cache_meta(), invalidate_screening_cache(), Drop cached WC1 payloads so the next screen uses fresh API + mapper logic., Drop cached WC1 payloads so the next screen uses fresh API + mapper logic., Drop cached WC1 payloads so the next screen uses fresh API + mapper logic., Return entity screening data from Redis cache or WC1 API.      On API success th, lseg_key(), ``lseg:v1:{name_normalized}:{entity_type}`` (+1 more)

### Community 59 - "Community 59"
Cohesion: 0.22
Nodes (9): get_case_score(), Return score breakdown and totalScore for a case., Return score breakdown and totalScore for a case., Return score breakdown and totalScore for a case., Return score breakdown and totalScore for a case., Return score breakdown and totalScore for a case., Return score breakdown and totalScore for a case., Return score breakdown and totalScore for a case. (+1 more)

### Community 60 - "Community 60"
Cohesion: 0.22
Nodes (9): _format_affiliate_tree_compact(), Template fallback for a single section when LLM call fails., Template fallback for a single section when LLM call fails., Template fallback for a single section when LLM call fails., Template fallback for a single section when LLM call fails., Template fallback for a single section when LLM call fails., Template fallback for a single section when LLM call fails., Template fallback for a single section when LLM call fails. (+1 more)

### Community 63 - "Community 63"
Cohesion: 0.39
Nodes (7): add_event_to_enriched(), append_case_event(), _coerce_dict(), _coerce_list(), _now_iso(), Append one verification log event into enriched_data dict.      Keeps payload sm, Load case, append one event, and persist enriched_data.

### Community 64 - "Community 64"
Cohesion: 0.25
Nodes (8): _collect_affiliate_enrichments(), Walk affiliate tree, load enriched_data for nodes with hasReport=True., Walk affiliate tree, load enriched_data for nodes with hasReport=True., Walk affiliate tree, load enriched_data for nodes with hasReport=True., Walk affiliate tree, load enriched_data for nodes with hasReport=True., Walk affiliate tree, load enriched_data for nodes with hasReport=True., Walk affiliate tree, load enriched_data for nodes with hasReport=True., Walk affiliate tree, load enriched_data for nodes with hasReport=True.

### Community 66 - "Community 66"
Cohesion: 0.57
Nodes (6): AdataError, download_company_report(), _fetch(), _poll(), run_parallel_checks(), RuntimeError

### Community 67 - "Community 67"
Cohesion: 0.33
Nodes (7): Re-run LSEG screening for all non-resident nodes in the affiliate tree., Re-run LSEG screening for all non-resident nodes in the affiliate tree., Re-run LSEG WC1 for one case and update risk score., Re-run LSEG screening for all non-resident nodes in the affiliate tree., Re-run LSEG WC1 for one case and update risk score., rescreen_case_lseg_endpoint(), rescreen_extended()

### Community 68 - "Community 68"
Cohesion: 0.29
Nodes (7): _company_data_from_info(), _fetch_enrichment_profile(), Fetch Adata /info for *iin* and return normalized enrichment dict., Fetch Adata /info for *iin* and return normalized enrichment dict., Fetch Adata /info for *iin* and return normalized enrichment dict., Fetch Adata /info for *iin* and return normalized enrichment dict., Fetch Adata /info for *iin* and return normalized enrichment dict.

### Community 71 - "Community 71"
Cohesion: 0.48
Nodes (5): addToRemoveQueue(), dispatch(), genId(), reducer(), toast()

### Community 72 - "Community 72"
Cohesion: 0.38
Nodes (3): injectRiskBadges(), processContent(), wrapTakeawayBlocks()

### Community 74 - "Community 74"
Cohesion: 0.53
Nodes (5): _deep_search(), _render_history(), _request(), _show_audit(), _show_status()

### Community 75 - "Community 75"
Cohesion: 0.33
Nodes (6): _extract_media(), Parse /media-check/results response into a compact list of articles., Parse /media-check/results response into a compact list of articles., Call WC1 for a single entity and return raw screening data.      Does NOT intera, Call WC1 for a single entity and return raw screening data.      Does NOT intera, _screen_entity()

### Community 76 - "Community 76"
Cohesion: 0.47
Nodes (5): analyze_court_cases(), _case_to_text(), _classify_single(), LLM-based analysis of court case texts.  Classifies each court case from Adata i, Add aiAnalysis field to each court case that lacks one. Returns updated list.

### Community 77 - "Community 77"
Cohesion: 0.33
Nodes (6): deep_find(), Return the first non-empty value for any key in ``keys`` (case-insensitive)., Return the first non-empty value for any key in ``keys`` (case-insensitive)., Return the first non-empty value for any key in ``keys`` (case-insensitive)., Return the first non-empty value for any key in ``keys`` (case-insensitive)., Return the first non-empty value for any key in ``keys`` (case-insensitive).

### Community 79 - "Community 79"
Cohesion: 0.4
Nodes (5): Backfill LSEG screening + re-score for all existing ready cases.      Idempotent, Backfill or refresh LSEG screening + re-score for ready cases.      With ``force, Backfill or refresh LSEG screening + re-score for ready cases.      With ``force, Backfill or refresh LSEG screening + re-score for ready cases.      With ``force, rescreen_all_with_lseg()

### Community 80 - "Community 80"
Cohesion: 0.4
Nodes (5): generate_case_full_report(), Запустить генерацию полного AI-отчёта в фоне., Запустить генерацию полного AI-отчёта в фоне., Запустить генерацию полного AI-отчёта в фоне., Запустить генерацию полного AI-отчёта в фоне.

### Community 92 - "Community 92"
Cohesion: 0.67
Nodes (3): _ensure_test_database(), Isolate tests from developer PostgreSQL data., _test_database_url()

### Community 93 - "Community 93"
Cohesion: 0.83
Nodes (3): _copy_table(), migrate(), _sqlite_path()

## Knowledge Gaps
- **429 isolated node(s):** `Compatibility shim for legacy imports.`, `HTTP Basic auth against users stored in PostgreSQL.`, `Settings`, `Ensure company API prefix; fix common ``/api`` without ``/company`` typo.`, `Derive Adata *individual* API base from the company base URL.` (+424 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `str` connect `Community 0` to `Community 1`, `Community 3`, `Community 4`, `Community 6`, `Community 7`, `Community 8`, `Community 9`, `Community 13`, `Community 14`, `Community 15`, `Community 18`, `Community 19`, `Community 20`, `Community 26`, `Community 28`, `Community 29`, `Community 31`, `Community 32`, `Community 33`, `Community 34`, `Community 35`, `Community 36`, `Community 39`, `Community 40`, `Community 41`, `Community 42`, `Community 44`, `Community 48`, `Community 49`, `Community 57`, `Community 63`, `Community 76`, `Community 97`?**
  _High betweenness centrality (0.345) - this node is a cross-community bridge._
- **Why does `process_case()` connect `Community 35` to `Community 0`, `Community 2`, `Community 36`, `Community 68`, `Community 4`, `Community 8`, `Community 40`, `Community 44`, `Community 76`, `Community 13`, `Community 48`, `Community 18`, `Community 21`, `Community 54`, `Community 57`, `Community 63`?**
  _High betweenness centrality (0.082) - this node is a cross-community bridge._
- **Why does `CompanyData` connect `Community 21` to `Community 97`, `Community 3`, `Community 68`, `Community 37`, `Community 40`, `Community 16`, `Community 50`, `Community 20`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Are the 72 inferred relationships involving `str` (e.g. with `save_audit()` and `update_pdf_path()`) actually correct?**
  _`str` has 72 INFERRED edges - model-reasoned connections that need verification._
- **Are the 22 inferred relationships involving `process_case()` (e.g. with `lookup_company()` and `case_pipeline_task()`) actually correct?**
  _`process_case()` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `map_info_data()` (e.g. with `_company_data_from_info()` and `str`) actually correct?**
  _`map_info_data()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `AdataProvider` (e.g. with `lifespan()` and `_ensure_worker_context()`) actually correct?**
  _`AdataProvider` has 13 INFERRED edges - model-reasoned connections that need verification._