from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.core.config import settings
from app.models import db
from app.services.adata.client import AdataError, fetch_pdf_report_url
from app.models.schemas import (
    ChatRequest,
    CheckDuplicatesRequest,
    DocumentRequest,
    DuplicatePolicy,
    LookupRequest,
    ParseBinsRequest,
    UploadCasesRequest,
)
from app.models.serializers import case_to_api
from app.services.ai.service import AIService
from app.services.affiliate_tree import (
    _empty_tree_meta,
    _merge_tree_into_enriched,
    get_cached_node_report,
    normalize_bin,
)
from app.services.import_parser import (
    parse_bins_text,
    parse_import_file,
    preview_import_rows,
)
from app.services.ai.full_report import generate_full_report
from app.services.pipeline import process_case, rescreen_case_lseg, rescreen_lseg_extended

logger = logging.getLogger(__name__)
from app.services.queue import (
    enqueue_affiliate_tree,
    enqueue_ai_conclusion,
    enqueue_case_pipeline,
    enqueue_chat_reply,
)

router = APIRouter(prefix="/api", tags=["cases"])
_ai = AIService()


def _normalize_upload_iin(raw: str) -> str:
    return "".join(ch for ch in raw if ch.isdigit())


def _link_parent_case(
    case_row: dict[str, Any], parent_case_id: str | None
) -> dict[str, Any]:
    if not parent_case_id or case_row.get("parent_case_id"):
        return case_row
    db.update_case(case_row["id"], parent_case_id=parent_case_id)
    linked = db.get_case(case_row["id"])
    return linked if linked is not None else case_row


async def _import_upload_item(
    *,
    name: str,
    iin_bin: str,
    on_duplicate: DuplicatePolicy,
) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    """Returns (action, api_case, job_or_none). action: created | skipped | refreshed."""
    iin = _normalize_upload_iin(iin_bin)
    if len(iin) != 12:
        raise HTTPException(status_code=400, detail=f"IIN/BIN must be 12 digits: {iin_bin}")

    existing = db.find_case_by_iin(iin)
    if existing and on_duplicate != "create":
        case_id = existing["id"]
        if on_duplicate == "skip":
            row = db.get_case(case_id)
            if row is None:
                raise HTTPException(status_code=500, detail="Case not found")
            return "skipped", case_to_api(row), None  # keep original parent_case_id
        if on_duplicate == "refresh":
            db.update_case(case_id, status="pending", company_name=name)
            job = await enqueue_case_pipeline(case_id)
            row = db.get_case(case_id)
            if row is None:
                raise HTTPException(status_code=500, detail="Case not found")
            return "refreshed", case_to_api(row), job

    row = db.create_case(company_name=name, iin=iin)
    job = await enqueue_case_pipeline(row["id"])
    return "created", case_to_api(row), job


@router.post("/upload/check-duplicates")
def check_upload_duplicates(payload: CheckDuplicatesRequest) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in payload.iinBins:
        iin = _normalize_upload_iin(raw)
        if len(iin) != 12 or iin in seen:
            continue
        seen.add(iin)
        existing = db.find_case_by_iin(iin)
        if existing is None:
            continue
        matches.append(
            {
                "iinBin": iin,
                "existingCaseId": existing["id"],
                "name": existing.get("company_name"),
                "status": existing.get("status"),
                "riskLevel": existing.get("risk_level"),
            }
        )
    return {"matches": matches, "count": len(matches)}


@router.post("/upload/parse-bins")
def parse_bins_upload(payload: ParseBinsRequest) -> dict[str, Any]:
    items = parse_bins_text(payload.text)
    rows = preview_import_rows(items)
    return {"rows": rows, "count": len(rows)}


@router.post("/upload/parse")
async def parse_upload_file(file: UploadFile = File(...)) -> dict[str, Any]:
    filename = file.filename or ""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is empty")

    lower = filename.lower()
    if not lower.endswith((".xlsx", ".xls", ".docx", ".txt", ".csv")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Use .xlsx, .xls, .docx, .txt, or .csv",
        )

    try:
        items = parse_import_file(filename, content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}") from exc

    rows = preview_import_rows(items)
    return {"rows": rows, "count": len(rows)}


@router.post("/upload")
async def upload_cases(
    request: Request,
) -> dict[str, Any]:
    items: list[dict[str, str]] = []
    on_duplicate: DuplicatePolicy = "create"
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise HTTPException(status_code=400, detail="Missing file field")
        filename = getattr(upload, "filename", "") or ""
        content = await upload.read()  # type: ignore[union-attr]
        if not content:
            raise HTTPException(status_code=400, detail="File is empty")
        try:
            parsed = parse_import_file(filename, content)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}") from exc
        preview = preview_import_rows(parsed)
        items = [
            {"name": row["name"], "iinBin": row["iinBin"]}
            for row in preview
            if row["valid"]
        ]
    else:
        payload = UploadCasesRequest.model_validate(await request.json())
        on_duplicate = payload.onDuplicate
        items = [{"name": c.name, "iinBin": c.iinBin} for c in payload.cases]

    if not items:
        raise HTTPException(status_code=400, detail="No valid cases found")

    created: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    stats = {"created": 0, "skipped": 0, "refreshed": 0}

    for item in items:
        action, api_case, job = await _import_upload_item(
            name=item["name"],
            iin_bin=item["iinBin"],
            on_duplicate=on_duplicate,
        )
        created.append(api_case)
        if job:
            jobs.append(job)
        stats[action] += 1  # type: ignore[literal-required]

    return {
        "cases": created,
        "count": len(created),
        "jobs": jobs,
        **stats,
    }


@router.get("/cases")
def list_cases() -> list[dict[str, Any]]:
    return [case_to_api(row) for row in db.list_cases()]


@router.post("/lookup")
async def lookup_company(
    payload: LookupRequest,
) -> dict[str, Any]:
    iin = "".join(ch for ch in payload.iinBin if ch.isdigit())
    if len(iin) != 12:
        raise HTTPException(status_code=400, detail="IIN/BIN must be 12 digits")

    if payload.parentCaseId:
        parent = db.get_case(payload.parentCaseId)
        if parent:
            cached = get_cached_node_report(parent, iin)
            if cached:
                open_id = cached.get("openCaseId")
                if open_id:
                    row = db.get_case(open_id)
                    if row is not None:
                        row = _link_parent_case(row, payload.parentCaseId)
                        return case_to_api(row)
                # Cache-only snapshot: create or enqueue a real case below.

    existing = db.find_case_by_iin(iin)
    if existing and existing.get("status") == "ready":
        existing = _link_parent_case(existing, payload.parentCaseId)
        return case_to_api(existing)

    if existing:
        case_id = existing["id"]
        existing = _link_parent_case(existing, payload.parentCaseId)
        case_id = existing["id"]
        if payload.sync:
            db.update_case(case_id, status="pending", company_name=payload.name)
    else:
        row = db.create_case(
            company_name=payload.name,
            iin=iin,
            parent_case_id=payload.parentCaseId,
        )
        case_id = row["id"]

    if payload.sync:
        await process_case(case_id)
        await enqueue_affiliate_tree(case_id)
        await enqueue_ai_conclusion(case_id)
    else:
        await enqueue_case_pipeline(case_id)

    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Case not found after lookup")
    return case_to_api(row)


@router.post("/cases/{case_id}/refresh")
async def refresh_case(case_id: str) -> dict[str, Any]:
    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")

    db.update_case(case_id, status="pending")
    job = await enqueue_case_pipeline(case_id)
    updated = db.get_case(case_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Case not found")
    return {**case_to_api(updated), "job": job}


@router.get("/cases/{case_id}")
def get_case(case_id: str) -> dict[str, Any]:
    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case_to_api(row)


@router.get("/cases/{case_id}/node-report")
def get_node_report(case_id: str, iinBin: str) -> dict[str, Any]:
    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    bin_val = normalize_bin(iinBin)
    if len(bin_val) != 12:
        raise HTTPException(status_code=400, detail="IIN/BIN must be 12 digits")

    report = get_cached_node_report(row, bin_val)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Нет сохранённых данных по этому БИН. "
                "Дождитесь построения дерева или нажмите «Перестроить»."
            ),
        )
    return report


@router.get("/cases/{case_id}/graph")
def get_case_graph(case_id: str) -> dict[str, Any]:
    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    enriched = row.get("enriched_data") or {}
    tree = enriched.get("affiliateTree")
    if isinstance(tree, dict):
        return tree
    return {"status": "pending", "depth": 2, "root": None, "nodesCount": 0}


@router.post("/cases/{case_id}/graph/build")
async def rebuild_case_graph(case_id: str) -> dict[str, Any]:
    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if row.get("status") != "ready":
        raise HTTPException(
            status_code=400,
            detail="Case must be ready before building affiliate tree",
        )

    enriched = row.get("enriched_data") or {}
    enriched = _merge_tree_into_enriched(enriched, _empty_tree_meta())
    enriched["affiliateTree"]["status"] = "building"
    db.update_case(case_id, enriched_data=enriched)
    job = await enqueue_affiliate_tree(case_id)
    return {"status": "building", "message": "Affiliate tree build started", "job": job}


@router.get("/cases/{case_id}/conclusion")
def get_conclusion(case_id: str) -> dict[str, str]:
    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"conclusion": row.get("conclusion") or ""}


@router.get("/ai/status")
def ai_status() -> dict[str, Any]:
    return {
        "openaiConfigured": _ai.uses_openai(),
        "model": settings.openai_model if _ai.uses_openai() else None,
    }


@router.get("/cases/{case_id}/report")
async def download_case_report(case_id: str) -> Response:
    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if not settings.adata_token:
        raise HTTPException(status_code=503, detail="ADATA_TOKEN is not configured")

    iin = row["iin"]
    try:
        pdf_url = await fetch_pdf_report_url(iin)
    except AdataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    timeout = max(settings.adata_timeout_seconds, 35.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            pdf_response = await client.get(pdf_url, follow_redirects=True)
            pdf_response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"PDF download failed: {exc}") from exc

    filename = f"adata-report-{iin}.pdf"
    return Response(
        content=pdf_response.content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/cases/{case_id}/chat")
async def post_chat(case_id: str, payload: ChatRequest) -> dict[str, Any]:
    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if row.get("status") != "ready":
        raise HTTPException(
            status_code=400,
            detail="Дождитесь завершения проверки (статус «готово»)",
        )

    user = db.add_chat_message(case_id=case_id, role="user", content=payload.message)
    job = await enqueue_chat_reply(case_id, payload.message)

    return {
        "status": "queued",
        "job": job,
        "userMessage": {
            "id": user["id"],
            "role": "user",
            "content": payload.message,
            "createdAt": user["created_at"],
        },
    }


@router.post("/cases/{case_id}/documents")
def post_document(case_id: str, payload: DocumentRequest) -> dict[str, Any]:
    if db.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found")

    analysis = payload.analysis
    if not analysis:
        analysis = (
            f"Документ «{payload.filename}» зарегистрирован. "
            "Автоматический анализ PDF доступен при подключении OpenAI."
        )

    doc = db.add_document(
        case_id=case_id,
        filename=payload.filename,
        file_type=payload.fileType,
        analysis=analysis,
    )
    return {
        "document": {
            "id": doc["id"],
            "filename": doc["filename"],
            "fileType": doc["file_type"],
            "uploadedAt": doc["uploaded_at"],
        }
    }


@router.post("/admin/rescreen")
async def rescreen_all_with_lseg(force: bool = False) -> dict[str, Any]:
    """Backfill or refresh LSEG screening + re-score for ready cases.

    With ``force=false`` (default), skips cases that already have ``lseg.screenedAt``.
    With ``force=true``, re-runs WC1 and invalidates Redis cache per case.
    """
    import asyncio as _asyncio

    rows = db.list_cases()
    ready = [r for r in rows if r.get("status") == "ready"]

    if not ready:
        return {"queued": 0, "message": "Нет кейсов в статусе ready"}

    async def _run() -> None:
        ok = err = skipped = 0
        for row in ready:
            cid = row["id"]
            enriched = row.get("enriched_data") or {}
            lseg_existing = enriched.get("lseg")
            if not force and lseg_existing and lseg_existing.get("screenedAt"):
                skipped += 1
                continue
            success = await rescreen_case_lseg(cid, force=force)
            if success:
                ok += 1
            else:
                err += 1
            await _asyncio.sleep(0.5)
        logger.info(
            "LSEG bulk rescreen finished: ok=%s err=%s skipped=%s force=%s",
            ok,
            err,
            skipped,
            force,
        )

    _asyncio.create_task(_run())

    verb = "перепроверка" if force else "дозаполнение"
    return {
        "queued": len(ready),
        "force": force,
        "message": f"Запущен фоновый LSEG {verb} для {len(ready)} кейсов",
    }


@router.post("/cases/{case_id}/rescreen-extended")
async def rescreen_extended(case_id: str) -> dict[str, Any]:
    """Re-run LSEG screening for all non-resident nodes in the affiliate tree."""
    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if row.get("status") != "ready":
        raise HTTPException(status_code=400, detail="Кейс должен быть в статусе ready")
    result = await rescreen_lseg_extended(case_id)
    return {"status": "ok", "screened": result}


@router.post("/cases/{case_id}/lseg/rescreen")
async def rescreen_case_lseg_endpoint(case_id: str, force: bool = True) -> dict[str, Any]:
    """Re-run LSEG WC1 for one case and update risk score."""
    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if row.get("status") != "ready":
        raise HTTPException(status_code=400, detail="Кейс должен быть в статусе ready")

    success = await rescreen_case_lseg(case_id, force=force)
    if not success:
        raise HTTPException(status_code=502, detail="LSEG screening failed")

    updated = db.get_case(case_id)
    enriched = (updated or {}).get("enriched_data") or {}
    return {
        "caseId": case_id,
        "riskLevel": updated.get("risk_level") if updated else None,
        "totalScore": enriched.get("totalScore"),
        "lseg": enriched.get("lseg"),
    }


@router.post("/cases/{case_id}/full-report")
async def generate_case_full_report(case_id: str, force: bool = False) -> dict[str, Any]:
    """Запустить генерацию полного AI-отчёта в фоне."""
    import asyncio as _asyncio

    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if row.get("status") != "ready":
        raise HTTPException(
            status_code=400, detail="Кейс должен быть в статусе ready"
        )
    if force:
        enriched = row.get("enriched_data") or {}
        # Keep the previous report until the new one is saved — clearing here
        # caused reports to vanish when the user navigated away mid-generation.
        enriched["fullReportStatus"] = "generating"
        db.update_case(case_id, enriched_data=enriched)

    _asyncio.create_task(generate_full_report(case_id))
    return {
        "status": "queued",
        "message": "Генерация полного отчёта запущена в фоне",
        "caseId": case_id,
        "force": force,
    }


@router.get("/cases/{case_id}/full-report")
def get_case_full_report(case_id: str) -> dict[str, Any]:
    """Получить готовый полный отчёт."""
    from app.services.ai.full_report_meta import (
        compute_full_report_staleness,
        estimate_full_report_context,
        full_report_meta_for_row,
    )

    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    enriched = row.get("enriched_data") or {}
    report = enriched.get("fullReport")
    meta = full_report_meta_for_row(row)
    context_estimate = estimate_full_report_context(row)
    staleness = compute_full_report_staleness(enriched)
    if not report:
        raise HTTPException(status_code=404, detail="Отчёт ещё не сгенерирован")
    return {
        "report": report,
        "generatedAt": enriched.get("fullReportGeneratedAt"),
        "stale": staleness["stale"],
        "staleMessage": staleness.get("message"),
        "graphBuiltAt": staleness.get("treeBuiltAt"),
        "contextEstimate": context_estimate,
        "fullReportStale": meta["fullReportStale"],
        "fullReportStaleMessage": meta.get("fullReportStaleMessage"),
    }


@router.get("/cases/{case_id}/full-report/meta")
def get_case_full_report_meta(case_id: str) -> dict[str, Any]:
    """Staleness and context size without loading report body."""
    from app.services.ai.full_report_meta import full_report_meta_for_row

    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    enriched = row.get("enriched_data") or {}
    return {
        "hasReport": bool(enriched.get("fullReport")),
        "generatedAt": enriched.get("fullReportGeneratedAt"),
        "status": enriched.get("fullReportStatus"),
        **full_report_meta_for_row(row),
    }


@router.get("/cases/{case_id}/score")
def get_case_score(case_id: str) -> dict[str, Any]:
    """Return score breakdown and totalScore for a case."""
    row = db.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")

    enriched = row.get("enriched_data") or {}
    return {
        "totalScore": enriched.get("totalScore"),
        "riskLevel": row.get("risk_level"),
        "breakdown": enriched.get("scoreBreakdown") or [],
        "lsegScreenedAt": (enriched.get("lseg") or {}).get("screenedAt"),
    }

