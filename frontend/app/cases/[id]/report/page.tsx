'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useCases } from '@/lib/cases-context'
import {
  Printer,
  ArrowLeft,
  CheckSquare,
  Square,
  FileText,
  TrendingUp,
  ShieldCheck,
  Gavel,
  Building2,
  Users,
  MessageSquare,
  AlertTriangle,
} from 'lucide-react'

const SECTIONS = [
  { id: 'companyInfo', label: 'Общие сведения о компании', icon: Building2 },
  { id: 'scoring', label: 'Скоринг риска (7 метрик)', icon: TrendingUp },
  { id: 'lseg', label: 'LSEG / Санкции и PEP', icon: ShieldCheck },
  { id: 'courts', label: 'Судебные дела', icon: Gavel },
  { id: 'taxes', label: 'Налоговая информация', icon: FileText },
  { id: 'affiliates', label: 'Аффилированные лица', icon: Users },
  { id: 'conclusion', label: 'Заключение ИИ', icon: MessageSquare },
  { id: 'assessment', label: 'Оценка рисков', icon: AlertTriangle },
]

const RISK_LABELS = { low: 'Низкий', medium: 'Средний', high: 'Высокий' } as const
const METRIC_LABELS: Record<string, string> = {
  sanctions: 'Международные санкции',
  courts: 'Судебная активность',
  taxes: 'Налоговый комплаенс',
  legal_status: 'Правовой статус',
  pep: 'PEP-скрининг',
  adverse_media: 'Негативные публикации',
  affiliate_risk: 'Риск аффилиатов',
}

export default function ReportBuilderPage() {
  const params = useParams()
  const router = useRouter()
  const { getCase } = useCases()

  const caseId = typeof params.id === 'string' ? params.id : Array.isArray(params.id) ? params.id[0] : ''
  const caseData = getCase(caseId)

  const [selected, setSelected] = useState<Set<string>>(
    new Set(SECTIONS.map((s) => s.id)),
  )
  const [officer, setOfficer] = useState('')
  const [confidentiality, setConfidentiality] = useState<'Internal' | 'Confidential'>('Internal')

  if (!caseData) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 text-center text-neutral-500">
        Дело не найдено.
      </div>
    )
  }

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const enrichment = caseData.enrichment
  const assessment = caseData.assessment
  const lseg = caseData.lseg
  const breakdown = caseData.scoreBreakdown || []

  const handlePrint = () => window.print()

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Controls — hidden on print */}
      <div className="print:hidden mb-8">
        <button
          onClick={() => router.back()}
          className="flex items-center gap-2 text-sm text-neutral-500 hover:text-neutral-900 mb-6"
        >
          <ArrowLeft className="w-4 h-4" />
          Назад
        </button>

        <div className="bg-white rounded-xl border border-neutral-200 p-6 mb-6">
          <h2 className="font-semibold text-neutral-900 mb-4">Настройка отчёта</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
            <div>
              <label className="block text-sm text-neutral-600 mb-1">Составил</label>
              <input
                type="text"
                value={officer}
                onChange={(e) => setOfficer(e.target.value)}
                placeholder="ФИО комплаенс-офицера"
                className="w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm text-neutral-600 mb-1">Уровень конфиденциальности</label>
              <select
                value={confidentiality}
                onChange={(e) => setConfidentiality(e.target.value as 'Internal' | 'Confidential')}
                className="w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="Internal">Internal</option>
                <option value="Confidential">Confidential</option>
              </select>
            </div>
          </div>

          <h3 className="text-sm font-medium text-neutral-700 mb-3">Разделы отчёта</h3>
          <div className="grid grid-cols-2 gap-2">
            {SECTIONS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => toggle(id)}
                className={`flex items-center gap-2 p-3 rounded-lg border text-sm text-left transition-colors ${
                  selected.has(id)
                    ? 'bg-blue-50 border-blue-200 text-blue-800'
                    : 'bg-neutral-50 border-neutral-200 text-neutral-500'
                }`}
              >
                {selected.has(id) ? (
                  <CheckSquare className="w-4 h-4 shrink-0" />
                ) : (
                  <Square className="w-4 h-4 shrink-0" />
                )}
                <Icon className="w-4 h-4 shrink-0" />
                {label}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={handlePrint}
          className="flex items-center gap-2 px-5 py-2.5 bg-neutral-900 hover:bg-neutral-800 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Printer className="w-4 h-4" />
          Скачать / Распечатать PDF
        </button>
      </div>

      {/* ── PRINTABLE REPORT ─────────────────────────────────────────────── */}
      <div className="bg-white print:shadow-none border border-neutral-200 print:border-0 rounded-xl p-8 print:p-0">
        {/* Cover */}
        <div className="border-b border-neutral-200 pb-6 mb-6">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs uppercase tracking-widest text-neutral-400 mb-1">
                Комплаенс-заключение
              </p>
              <h1 className="text-2xl font-bold text-neutral-900">{caseData.name}</h1>
              <p className="text-neutral-500 font-mono mt-1">{caseData.iinBin}</p>
            </div>
            <div className="text-right text-sm text-neutral-500">
              <p className={`font-semibold text-xs uppercase tracking-wide px-2 py-1 rounded ${confidentiality === 'Confidential' ? 'bg-red-100 text-red-700' : 'bg-neutral-100 text-neutral-600'}`}>
                {confidentiality}
              </p>
              <p className="mt-2">{new Date().toLocaleDateString('ru-RU')}</p>
              {officer && <p className="mt-1">Составил: {officer}</p>}
            </div>
          </div>

          {/* Risk summary */}
          {caseData.riskLevel && (
            <div className={`mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${
              caseData.riskLevel === 'high'
                ? 'bg-red-100 text-red-700'
                : caseData.riskLevel === 'medium'
                  ? 'bg-amber-100 text-amber-700'
                  : 'bg-emerald-100 text-emerald-700'
            }`}>
              Уровень риска: {RISK_LABELS[caseData.riskLevel]}
              {caseData.totalScore !== null && caseData.totalScore !== undefined && (
                <span className="opacity-70">· {caseData.totalScore.toFixed(1)} / 100</span>
              )}
            </div>
          )}
        </div>

        {/* Company Info */}
        {selected.has('companyInfo') && enrichment && (
          <section className="mb-6">
            <h2 className="text-base font-semibold text-neutral-900 mb-3 flex items-center gap-2">
              <Building2 className="w-4 h-4 text-blue-600" />
              Общие сведения
            </h2>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {[
                ['Полное наименование', enrichment.companyInfo.fullName],
                ['БИН/ИИН', caseData.iinBin],
                ['Дата регистрации', enrichment.companyInfo.registrationDate],
                ['Адрес', enrichment.companyInfo.address],
                ['Директор', enrichment.companyInfo.director],
                ['Отрасль', enrichment.companyInfo.industry],
              ].map(([k, v]) => (
                <div key={k}>
                  <p className="text-neutral-500">{k}</p>
                  <p className="font-medium text-neutral-900">{v || '—'}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Scoring */}
        {selected.has('scoring') && breakdown.length > 0 && (
          <section className="mb-6">
            <h2 className="text-base font-semibold text-neutral-900 mb-3 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-blue-600" />
              Скоринг риска
            </h2>
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-neutral-50 text-neutral-600 text-left">
                  <th className="px-3 py-2 font-medium border border-neutral-200">Метрика</th>
                  <th className="px-3 py-2 font-medium border border-neutral-200 w-24">Баллы</th>
                  <th className="px-3 py-2 font-medium border border-neutral-200">Источник</th>
                  <th className="px-3 py-2 font-medium border border-neutral-200">Обоснование</th>
                </tr>
              </thead>
              <tbody>
                {breakdown.map((m) => (
                  <tr key={m.metric} className="border-b border-neutral-100">
                    <td className="px-3 py-2 border border-neutral-200">{METRIC_LABELS[m.metric] || m.metric}</td>
                    <td className="px-3 py-2 border border-neutral-200 text-center font-mono">
                      {m.points.toFixed(1)}/{m.max_points}
                    </td>
                    <td className="px-3 py-2 border border-neutral-200 uppercase text-xs text-neutral-500">{m.source}</td>
                    <td className="px-3 py-2 border border-neutral-200 text-neutral-600">{m.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {/* LSEG */}
        {selected.has('lseg') && lseg && (
          <section className="mb-6">
            <h2 className="text-base font-semibold text-neutral-900 mb-3 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-purple-600" />
              LSEG World-Check One
            </h2>
            <div className="text-sm space-y-2">
              <p>Дата скрининга: {new Date(lseg.screenedAt).toLocaleString('ru-RU')}</p>
              <p>
                Санкции:{' '}
                <strong className={lseg.sanctions.isOnList ? 'text-red-600' : 'text-emerald-600'}>
                  {lseg.sanctions.isOnList
                    ? `Совпадение: ${lseg.sanctions.matchedLists.join(', ')}`
                    : 'Не числится'}
                </strong>
              </p>
              <p>
                PEP:{' '}
                <strong className={lseg.pep.isHit ? 'text-amber-600' : 'text-emerald-600'}>
                  {lseg.pep.isHit ? 'Совпадение' : 'Не выявлено'}
                </strong>
              </p>
              <p>
                Adverse Media:{' '}
                <strong>{lseg.adverseMedia.negativeCount > 0 ? `${lseg.adverseMedia.negativeCount} негативных публикаций` : 'Не выявлено'}</strong>
              </p>
            </div>
          </section>
        )}

        {/* Courts */}
        {selected.has('courts') && enrichment?.courts && (
          <section className="mb-6">
            <h2 className="text-base font-semibold text-neutral-900 mb-3 flex items-center gap-2">
              <Gavel className="w-4 h-4 text-amber-600" />
              Судебные дела
            </h2>
            <div className="text-sm grid grid-cols-3 gap-3 mb-3">
              <div>
                <p className="text-neutral-500">Активные</p>
                <p className="font-semibold text-lg">{enrichment.courts.activeCases}</p>
              </div>
              <div>
                <p className="text-neutral-500">Завершённые</p>
                <p className="font-semibold text-lg">{enrichment.courts.completedCases}</p>
              </div>
              <div>
                <p className="text-neutral-500">Общая сумма</p>
                <p className="font-semibold text-lg">
                  {new Intl.NumberFormat('ru-RU').format(enrichment.courts.totalAmount)} тг
                </p>
              </div>
            </div>
          </section>
        )}

        {/* Taxes */}
        {selected.has('taxes') && enrichment?.taxes && (
          <section className="mb-6">
            <h2 className="text-base font-semibold text-neutral-900 mb-3 flex items-center gap-2">
              <FileText className="w-4 h-4 text-green-600" />
              Налоги
            </h2>
            <div className="text-sm grid grid-cols-3 gap-3">
              <div>
                <p className="text-neutral-500">Задолженность</p>
                <p className="font-semibold">{new Intl.NumberFormat('ru-RU').format(enrichment.taxes.debt)} тг</p>
              </div>
              <div>
                <p className="text-neutral-500">Статус</p>
                <p className="font-semibold capitalize">{enrichment.taxes.status === 'clean' ? 'Чисто' : enrichment.taxes.status === 'debt' ? 'Задолженность' : 'Критично'}</p>
              </div>
              <div>
                <p className="text-neutral-500">Последний год</p>
                <p className="font-semibold">{enrichment.taxes.lastPayment}</p>
              </div>
            </div>
          </section>
        )}

        {/* Affiliates */}
        {selected.has('affiliates') && enrichment?.affiliates && (
          <section className="mb-6">
            <h2 className="text-base font-semibold text-neutral-900 mb-3 flex items-center gap-2">
              <Users className="w-4 h-4 text-neutral-600" />
              Аффилированные лица
            </h2>
            <div className="text-sm">
              {enrichment.affiliates.companies.length > 0 && (
                <div className="mb-3">
                  <p className="text-neutral-500 mb-1">Юридические лица ({enrichment.affiliates.companies.length})</p>
                  {enrichment.affiliates.companies.slice(0, 8).map((c, i) => (
                    <p key={i} className="text-neutral-700">• {c.name} ({c.iinBin}) — {c.role}</p>
                  ))}
                </div>
              )}
              {enrichment.affiliates.individuals.length > 0 && (
                <div>
                  <p className="text-neutral-500 mb-1">Физические лица ({enrichment.affiliates.individuals.length})</p>
                  {enrichment.affiliates.individuals.slice(0, 8).map((p, i) => (
                    <p key={i} className="text-neutral-700">• {p.name} ({p.iin}) — {p.role}</p>
                  ))}
                </div>
              )}
            </div>
          </section>
        )}

        {/* Assessment */}
        {selected.has('assessment') && assessment && (
          <section className="mb-6">
            <h2 className="text-base font-semibold text-neutral-900 mb-3 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              Оценка рисков
            </h2>
            <p className="text-sm text-neutral-700 mb-3">{assessment.summary}</p>
            {assessment.flags.length > 0 && (
              <ul className="space-y-1">
                {assessment.flags.map((f, i) => (
                  <li key={i} className={`text-sm px-3 py-1.5 rounded ${f.type === 'danger' ? 'bg-red-50 text-red-800' : 'bg-amber-50 text-amber-800'}`}>
                    {f.message}
                  </li>
                ))}
              </ul>
            )}
            {assessment.recommendations.length > 0 && (
              <div className="mt-3">
                <p className="text-sm font-medium text-neutral-700 mb-1">Рекомендации:</p>
                <ul className="space-y-1">
                  {assessment.recommendations.map((r, i) => (
                    <li key={i} className="text-sm text-neutral-600">• {r}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}

        {/* Conclusion */}
        {selected.has('conclusion') && caseData.conclusion && (
          <section className="mb-6">
            <h2 className="text-base font-semibold text-neutral-900 mb-3 flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-blue-600" />
              Заключение ИИ
            </h2>
            <div className="text-sm text-neutral-700 whitespace-pre-wrap border-l-2 border-blue-200 pl-4">
              {caseData.conclusion}
            </div>
          </section>
        )}

        {/* Footer */}
        <div className="border-t border-neutral-200 pt-4 mt-8 text-xs text-neutral-400 flex justify-between">
          <span>Сформировано системой Akashi Compliance</span>
          <span>{confidentiality} · {new Date().toLocaleDateString('ru-RU')}</span>
        </div>
      </div>

      <style jsx global>{`
        @media print {
          nav, header, .print\\:hidden { display: none !important; }
          body { background: white; }
        }
      `}</style>
    </div>
  )
}
