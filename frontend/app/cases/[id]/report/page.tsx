'use client'

import { useState, type ReactNode } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useCases } from '@/lib/cases-context'
import { Abbr } from '@/components/ui/abbr'
import {
  Printer,
  ArrowLeft,
  CheckSquare,
  Square,
  FileText,
  ShieldCheck,
  Gavel,
  Building2,
  Users,
  MessageSquare,
  AlertTriangle,
} from 'lucide-react'

const SECTIONS = [
  { id: 'companyInfo', label: 'Общие сведения о компании', icon: Building2 },
  { id: 'lseg', label: 'LSEG / Санкции и PEP', icon: ShieldCheck },
  { id: 'courts', label: 'Судебные дела', icon: Gavel },
  { id: 'taxes', label: 'Налоговая информация', icon: FileText },
  { id: 'affiliates', label: 'Аффилированные лица', icon: Users },
  { id: 'conclusion', label: 'Заключение ИИ', icon: MessageSquare },
  { id: 'assessment', label: 'Выявленные факторы', icon: AlertTriangle },
]

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
        </div>

        {/* Company Info */}
        {selected.has('companyInfo') && enrichment && (
          <section className="mb-6">
            <h2 className="text-base font-semibold text-neutral-900 mb-3 flex items-center gap-2">
              <Building2 className="w-4 h-4 text-blue-600" />
              Общие сведения
            </h2>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {([
                ['Полное наименование', enrichment.companyInfo.fullName],
                [<><Abbr code="БИН">БИН</Abbr>/<Abbr code="ИИН">ИИН</Abbr></>, caseData.iinBin],
                ['Дата регистрации', enrichment.companyInfo.registrationDate],
                ['Адрес', enrichment.companyInfo.address],
                ['Директор', enrichment.companyInfo.director],
                ['Отрасль', enrichment.companyInfo.industry],
              ] as [ReactNode, string | undefined][]).map(([k, v], i) => (
                <div key={i}>
                  <p className="text-neutral-500">{k}</p>
                  <p className="font-medium text-neutral-900">{v || '—'}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* LSEG */}
        {selected.has('lseg') && lseg && (
          <section className="mb-6">
            <h2 className="text-base font-semibold text-neutral-900 mb-3 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-purple-600" />
              <Abbr code="LSEG">LSEG</Abbr> World-Check One
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
                <Abbr code="PEP">PEP</Abbr>:{' '}
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
        {selected.has('assessment') && assessment && assessment.flags.length > 0 && (
          <section className="mb-6">
            <h2 className="text-base font-semibold text-neutral-900 mb-3 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-neutral-500" />
              Выявленные факторы
            </h2>
            <ul className="space-y-1">
              {assessment.flags.map((f, i) => (
                <li key={i} className="text-sm px-3 py-1.5 rounded bg-neutral-50 text-neutral-700">
                  {f.message}
                </li>
              ))}
            </ul>
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
