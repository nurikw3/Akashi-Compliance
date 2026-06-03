'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import {
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  FileText,
  Loader2,
  Printer,
  RefreshCw,
} from 'lucide-react'
import { useCases } from '@/lib/cases-context'
import { fetchFullReport, fetchFullReportMeta, generateFullReport } from '@/lib/api'
import { LoadingGif } from '@/components/loading-gif'
import { ReportViewer } from '@/components/report-viewer'
import type { Case, FullReportContextEstimate } from '@/lib/types'

function ContextEstimatePanel({ estimate }: { estimate: FullReportContextEstimate }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mb-4 print:hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 text-sm text-neutral-600 hover:text-neutral-900"
      >
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        Размер контекста для ИИ ({estimate.model}, окно {estimate.contextWindowTokens / 1000}k)
      </button>
      {open && (
        <div className="mt-2 text-sm text-neutral-600 bg-neutral-50 border border-neutral-200 rounded-lg px-4 py-3 space-y-2">
          <p>
            ~{estimate.approxTotalInputTokens.toLocaleString('ru-RU')} токенов ввода суммарно по{' '}
            {estimate.sectionCalls} запросам (секции: санкции, суды, структура, резюме). На один
            запрос — не более окна модели; запас ~{estimate.headroomTokens.toLocaleString('ru-RU')}{' '}
            токенов.
          </p>
          <ul className="text-xs font-mono space-y-1">
            {Object.entries(estimate.sections).map(([key, s]) => (
              <li key={key}>
                {key}: {s.approxTokens.toLocaleString('ru-RU')} tok ({s.chars.toLocaleString('ru-RU')}{' '}
                / cap {s.capChars.toLocaleString('ru-RU')} симв.)
              </li>
            ))}
          </ul>
          <p className="text-xs text-neutral-500">{estimate.note}</p>
        </div>
      )}
    </div>
  )
}

export default function FullReportPage() {
  const params = useParams()
  const { getCase, refreshCase } = useCases()
  const caseId =
    typeof params.id === 'string'
      ? params.id
      : Array.isArray(params.id)
        ? params.id[0]
        : ''

  const caseData = getCase(caseId) as Case | undefined
  const [report, setReport] = useState<string | null>(null)
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [stale, setStale] = useState(false)
  const [staleMessage, setStaleMessage] = useState<string | null>(null)
  const [contextEstimate, setContextEstimate] = useState<FullReportContextEstimate | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const applyMeta = useCallback((meta: {
    fullReportStale?: boolean
    fullReportStaleMessage?: string | null
    fullReportContextEstimate?: FullReportContextEstimate | null
  }) => {
    setStale(Boolean(meta.fullReportStale))
    setStaleMessage(meta.fullReportStaleMessage ?? null)
    if (meta.fullReportContextEstimate) {
      setContextEstimate(meta.fullReportContextEstimate)
    }
  }, [])

  const loadMeta = useCallback(async () => {
    if (!caseId) return
    try {
      const meta = await fetchFullReportMeta(caseId)
      applyMeta(meta)
    } catch {
      /* ignore */
    }
  }, [caseId, applyMeta])

  const loadReport = useCallback(async () => {
    if (!caseId) return
    setError(null)
    try {
      const data = await fetchFullReport(caseId)
      setReport(data.report)
      setGeneratedAt(data.generatedAt)
      setStale(Boolean(data.stale))
      setStaleMessage(data.staleMessage ?? null)
      if (data.contextEstimate) setContextEstimate(data.contextEstimate)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Ошибка загрузки'
      if (msg.includes('404') || msg.includes('не сгенерирован')) {
        setReport(null)
        setGeneratedAt(null)
        await loadMeta()
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }, [caseId, loadMeta])

  useEffect(() => {
    if (!caseId) return
    void refreshCase(caseId)
    void loadReport()
  }, [caseId, refreshCase, loadReport])

  useEffect(() => {
    if (caseData) {
      applyMeta(caseData)
      if (caseData.fullReportContextEstimate) {
        setContextEstimate(caseData.fullReportContextEstimate)
      }
    }
  }, [caseData, applyMeta])

  useEffect(() => {
    if (!caseId) return
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        void refreshCase(caseId)
        void loadMeta()
        if (report) void loadReport()
        else void loadReport()
      }
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [caseId, refreshCase, loadMeta, loadReport, report])

  const handleGenerate = async () => {
    if (!caseId) return
    const previousGeneratedAt = generatedAt
    setGenerating(true)
    setError(null)
    setStale(false)
    try {
      await generateFullReport(caseId, true)
      for (let i = 0; i < 12; i++) {
        await new Promise((r) => setTimeout(r, 2500))
        try {
          const data = await fetchFullReport(caseId)
          if (previousGeneratedAt && data.generatedAt === previousGeneratedAt) {
            continue
          }
          setReport(data.report)
          setGeneratedAt(data.generatedAt)
          setStale(Boolean(data.stale))
          setStaleMessage(data.staleMessage ?? null)
          if (data.contextEstimate) setContextEstimate(data.contextEstimate)
          await refreshCase(caseId)
          setGenerating(false)
          return
        } catch {
          /* still generating */
        }
      }
      setError('Отчёт ещё формируется. Нажмите «Обновить» через несколько секунд.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось запустить генерацию')
    } finally {
      setGenerating(false)
    }
  }

  const title = caseData?.name ?? 'Контрагент'
  const isRegenerating =
    caseData?.fullReportStatus === 'generating' || generating
  const displayStale = stale || caseData?.fullReportStale
  const displayStaleMessage =
    staleMessage || caseData?.fullReportStaleMessage || null
  const estimate = contextEstimate ?? caseData?.fullReportContextEstimate ?? null
  const regenerateLabel = displayStale
    ? 'Пересоздать с учётом графа'
    : report
      ? 'Пересоздать'
      : 'Сгенерировать'

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link
        href={`/cases/${caseId}`}
        className="inline-flex items-center gap-2 text-sm text-neutral-500 hover:text-neutral-900 mb-6 print:hidden"
      >
        <ArrowLeft className="w-4 h-4" />
        Назад к делу
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4 mb-6 print:hidden">
        <div>
          <p className="text-xs uppercase tracking-widest text-neutral-400 mb-1">
            Комплексный отчёт (ИИ)
          </p>
          <h1 className="text-2xl font-bold text-neutral-900">{title}</h1>
          {generatedAt && (
            <p className="text-sm text-neutral-500 mt-1">
              Сформирован: {new Date(generatedAt).toLocaleString('ru-RU')}
            </p>
          )}
          {caseData?.graphBuiltAt && (
            <p className="text-sm text-neutral-500">
              Дерево связей: {new Date(caseData.graphBuiltAt).toLocaleString('ru-RU')}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {report && (
            <button
              type="button"
              onClick={() => window.print()}
              className="flex items-center gap-2 px-3 py-2.5 border border-neutral-200 rounded-lg text-sm font-medium text-neutral-600 hover:bg-neutral-50"
            >
              <Printer className="w-4 h-4" />
              Печать
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              setLoading(true)
              void loadReport()
              void loadMeta()
            }}
            disabled={loading || generating}
            className="flex items-center gap-2 px-4 py-2.5 border border-neutral-200 rounded-lg text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Обновить
          </button>
          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium disabled:opacity-50 ${
              displayStale
                ? 'bg-amber-600 hover:bg-amber-700 text-white'
                : 'bg-neutral-900 hover:bg-neutral-800 text-white'
            }`}
          >
            {generating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <FileText className="w-4 h-4" />
            )}
            {regenerateLabel}
          </button>
        </div>
      </div>

      {estimate && <ContextEstimatePanel estimate={estimate} />}

      {displayStale && displayStaleMessage && (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-sm text-amber-950 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 mb-4 print:hidden">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-5 h-5 shrink-0 text-amber-600 mt-0.5" />
            <p>{displayStaleMessage}</p>
          </div>
          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating}
            className="shrink-0 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-lg disabled:opacity-50"
          >
            {generating ? 'Формируем…' : 'Пересоздать отчёт'}
          </button>
        </div>
      )}

      {error && (
        <p className="text-sm text-red-600 mb-4 print:hidden">{error}</p>
      )}

      {isRegenerating && report && (
        <p className="text-sm text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-4 py-3 mb-4 print:hidden">
          Обновляем отчёт в фоне. Ниже показана предыдущая версия до завершения генерации.
        </p>
      )}

      {loading && !report ? (
        <LoadingGif message="Загружаем отчёт…" />
      ) : !report ? (
        <div className="bg-white rounded-xl border border-neutral-200 p-10 text-center">
          <FileText className="w-10 h-10 text-neutral-300 mx-auto mb-3" />
          <p className="text-neutral-600 mb-2">Полный отчёт ещё не создан</p>
          <p className="text-sm text-neutral-400 mb-6">
            В отчёт войдут LSEG, санкции учредителей, скоринг и рекомендация.
            {caseData?.affiliateTree?.nodesCount
              ? ` Дерево: ${caseData.affiliateTree.nodesCount} узлов.`
              : ''}
          </p>
          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-neutral-900 text-white rounded-lg text-sm font-medium"
          >
            {generating && <Loader2 className="w-4 h-4 animate-spin" />}
            Сгенерировать отчёт
          </button>
        </div>
      ) : (
        <div className="print:py-2">
          <ReportViewer markdown={report} />
        </div>
      )}
    </div>
  )
}
