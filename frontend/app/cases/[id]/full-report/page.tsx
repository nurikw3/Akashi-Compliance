'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { ArrowLeft, FileText, Loader2, Printer, RefreshCw } from 'lucide-react'
import { useCases } from '@/lib/cases-context'
import { fetchFullReport, generateFullReport } from '@/lib/api'
import { LoadingGif } from '@/components/loading-gif'
import { ReportViewer } from '@/components/report-viewer'

export default function FullReportPage() {
  const params = useParams()
  const { getCase } = useCases()
  const caseId =
    typeof params.id === 'string'
      ? params.id
      : Array.isArray(params.id)
        ? params.id[0]
        : ''

  const caseData = getCase(caseId)
  const [report, setReport] = useState<string | null>(null)
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadReport = useCallback(async () => {
    if (!caseId) return
    setError(null)
    try {
      const data = await fetchFullReport(caseId)
      setReport(data.report)
      setGeneratedAt(data.generatedAt)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Ошибка загрузки'
      if (msg.includes('404') || msg.includes('не сгенерирован')) {
        setReport(null)
        setGeneratedAt(null)
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }, [caseId])

  useEffect(() => {
    void loadReport()
  }, [loadReport])

  const handleGenerate = async () => {
    if (!caseId) return
    const previousGeneratedAt = generatedAt
    setGenerating(true)
    setError(null)
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
        </div>
        <div className="flex items-center gap-2">
          {report && (
            <button
              type="button"
              onClick={() => window.print()}
              className="flex items-center gap-2 px-3 py-2.5 border border-neutral-200 rounded-lg text-sm font-medium text-neutral-600 hover:bg-neutral-50 print:hidden"
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
            className="flex items-center gap-2 px-4 py-2.5 bg-neutral-900 hover:bg-neutral-800 text-white rounded-lg text-sm font-medium disabled:opacity-50"
          >
            {generating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <FileText className="w-4 h-4" />
            )}
            {report ? 'Пересоздать' : 'Сгенерировать'}
          </button>
        </div>
      </div>

      {error && (
        <p className="text-sm text-red-600 mb-4 print:hidden">{error}</p>
      )}

      {loading && !report ? (
        <LoadingGif message="Загружаем отчёт…" />
      ) : !report ? (
        <div className="bg-white rounded-xl border border-neutral-200 p-10 text-center">
          <FileText className="w-10 h-10 text-neutral-300 mx-auto mb-3" />
          <p className="text-neutral-600 mb-2">Полный отчёт ещё не создан</p>
          <p className="text-sm text-neutral-400 mb-6">
            В отчёт войдут LSEG, санкции учредителей, скоринг и рекомендация.
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
