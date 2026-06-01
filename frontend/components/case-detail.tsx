'use client'

import { useState, useRef, useEffect, type RefObject } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import {
  Building2,
  Gavel,
  AlertTriangle,
  FileText,
  MessageSquare,
  Upload,
  File,
  X,
  Send,
  Loader2,
  Network,
  Download,
  ShieldCheck,
  TrendingUp,
  Globe,
} from 'lucide-react'
import { downloadCaseReport, fetchAiStatus, rescreenAllWithLseg } from '@/lib/api'
import { useCases } from '@/lib/cases-context'
import { AffiliatesGraph } from '@/components/affiliates-graph'
import { LoadingGif } from '@/components/loading-gif'
import { MarkdownContent } from '@/components/markdown-content'
import { dataSourceLabel, sectionSource } from '@/lib/data-source-label'
import { caseDisplayName, formatPersonField } from '@/lib/case-display'
import type { Case, DataSourceKind, ScoreMetric, LsegData, LsegSanctionHit, LsegExtendedEntity } from '@/lib/types'

type Tab = 'data' | 'documents' | 'assessment' | 'chat' | 'scoring' | 'lseg'

const VALID_TABS: Tab[] = ['data', 'documents', 'assessment', 'chat', 'scoring', 'lseg']

function SectionHeading({
  icon: Icon,
  iconClassName,
  title,
  source,
}: {
  icon: typeof Building2
  iconClassName: string
  title: string
  source: DataSourceKind
}) {
  return (
    <div className="flex items-center gap-2 mb-4 flex-wrap">
      <Icon className={`w-5 h-5 ${iconClassName}`} />
      <h3 className="font-semibold text-neutral-900">{title}</h3>
      <span className="text-xs font-normal text-neutral-400">{dataSourceLabel(source)}</span>
    </div>
  )
}

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('ru-RU').format(amount) + ' тг'
}

function DataTab({ caseData, onRefresh }: { caseData: Case; onRefresh?: () => void }) {
  const { enrichment, dataSources } = caseData
  const displayName = caseDisplayName(caseData)
  const src = (section: Parameters<typeof sectionSource>[1]) =>
    sectionSource(dataSources, section)

  if (!enrichment) {
    return <LoadingGif message="Загружаем данные контрагента…" />
  }

  return (
    <div className="space-y-6">
      {/* Affiliates Graph - Main Feature */}
      <AffiliatesGraph
        caseId={caseData.id}
        mainCompany={{ name: displayName, iinBin: caseData.iinBin }}
        affiliateTree={caseData.affiliateTree}
        source={src('graph')}
        onTreeUpdated={onRefresh}
        lseg={caseData.lseg}
        lsegExtended={caseData.lsegExtended}
        affiliateProfiles={caseData.affiliateProfiles}
        beneficiary={caseData.beneficiary}
      />

      {/* Company Info */}
      <div className="bg-white rounded-xl border border-neutral-200 p-5">
        <SectionHeading
          icon={Building2}
          iconClassName="text-blue-600"
          title="Информация о компании"
          source={src('companyInfo')}
        />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-neutral-500">Полное наименование</p>
            <p className="text-neutral-900 font-medium">{enrichment.companyInfo.fullName}</p>
          </div>
          <div>
            <p className="text-neutral-500">Дата регистрации</p>
            <p className="text-neutral-900">{enrichment.companyInfo.registrationDate}</p>
          </div>
          <div>
            <p className="text-neutral-500">Адрес</p>
            <p className="text-neutral-900">{enrichment.companyInfo.address}</p>
          </div>
          <div>
            <p className="text-neutral-500">Директор</p>
            <p className="text-neutral-900">{formatPersonField(enrichment.companyInfo.director)}</p>
          </div>
          <div>
            <p className="text-neutral-500">Количество сотрудников</p>
            <p className="text-neutral-900">{enrichment.companyInfo.employees}</p>
          </div>
          <div>
            <p className="text-neutral-500">Отрасль</p>
            <p className="text-neutral-900">{enrichment.companyInfo.industry}</p>
          </div>
          {enrichment.companyInfo.operatingStatus && (
            <div>
              <p className="text-neutral-500">Статус (Adata)</p>
              <p className="text-neutral-900 capitalize">{enrichment.companyInfo.operatingStatus}</p>
            </div>
          )}
          {enrichment.companyInfo.legalForm && (
            <div>
              <p className="text-neutral-500">ОПФ</p>
              <p className="text-neutral-900">{enrichment.companyInfo.legalForm}</p>
            </div>
          )}
          {enrichment.companyInfo.ownership && (
            <div>
              <p className="text-neutral-500">Форма собственности</p>
              <p className="text-neutral-900">{enrichment.companyInfo.ownership}</p>
            </div>
          )}
          {enrichment.companyInfo.sourceLink && (
            <div className="md:col-span-2">
              <p className="text-neutral-500">Карточка Adata</p>
              <a
                href={enrichment.companyInfo.sourceLink}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline text-sm break-all"
              >
                {enrichment.companyInfo.sourceLink}
              </a>
            </div>
          )}
        </div>
      </div>

      {(enrichment.statusFlags?.length ?? 0) > 0 && (
        <div className="bg-white rounded-xl border border-neutral-200 p-5">
          <SectionHeading
            icon={AlertTriangle}
            iconClassName="text-amber-600"
            title="Статус предприятия"
            source={src('companyInfo')}
          />
          <ul className="space-y-2">
            {enrichment.statusFlags!.map((flag, i) => (
              <li
                key={i}
                className="text-sm text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2"
              >
                {flag}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Taxes */}
      <div className="bg-white rounded-xl border border-neutral-200 p-5">
        <SectionHeading
          icon={FileText}
          iconClassName="text-green-600"
          title="Налоговая информация"
          source={src('taxes')}
        />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div>
            <p className="text-neutral-500">Статус</p>
            <p className={`font-medium ${
              enrichment.taxes.status === 'clean' ? 'text-green-600' :
              enrichment.taxes.status === 'debt' ? 'text-amber-600' : 'text-red-600'
            }`}>
              {enrichment.taxes.status === 'clean' ? 'Без задолженности' :
               enrichment.taxes.status === 'debt' ? 'Есть задолженность' : 'Критическая задолженность'}
            </p>
          </div>
          <div>
            <p className="text-neutral-500">Задолженность</p>
            <p className="text-neutral-900">{formatCurrency(enrichment.taxes.debt)}</p>
          </div>
          <div>
            <p className="text-neutral-500">Последний год отчислений</p>
            <p className="text-neutral-900">{enrichment.taxes.lastPayment}</p>
          </div>
          {enrichment.taxes.totalPaid != null && enrichment.taxes.totalPaid > 0 && (
            <div>
              <p className="text-neutral-500">Всего уплачено (taxDeductions)</p>
              <p className="text-neutral-900">{formatCurrency(enrichment.taxes.totalPaid)}</p>
            </div>
          )}
        </div>
        {(enrichment.taxes.yearlyPayments?.length ?? 0) > 0 && (
          <div className="mt-4 border-t border-neutral-100 pt-4">
            <p className="text-sm text-neutral-500 mb-2">Отчисления по годам</p>
            <div className="flex flex-wrap gap-2">
              {enrichment.taxes.yearlyPayments!.slice(0, 8).map((row) => (
                <span
                  key={row.year}
                  className="text-xs bg-neutral-50 border border-neutral-100 rounded-lg px-2.5 py-1.5"
                >
                  {row.year}: {formatCurrency(row.amount)}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Courts */}
      <div className="bg-white rounded-xl border border-neutral-200 p-5">
        <SectionHeading
          icon={Gavel}
          iconClassName="text-amber-600"
          title={
            enrichment.courts.scope === 'director'
              ? 'Судебные дела (руководитель)'
              : 'Судебные дела'
          }
          source={src('courts')}
        />
        {enrichment.courts.note && (
          <p className="text-sm text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 mb-4">
            {enrichment.courts.note}
          </p>
        )}
        {src('courts') === 'adata' ||
        enrichment.courts.activeCases > 0 ||
        enrichment.courts.completedCases > 0 ||
        enrichment.courts.cases.length > 0 ? (
        <>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm mb-4">
          <div>
            <p className="text-neutral-500">Активные дела</p>
            <p className="text-neutral-900 font-medium">{enrichment.courts.activeCases}</p>
          </div>
          <div>
            <p className="text-neutral-500">Завершенные дела</p>
            <p className="text-neutral-900">{enrichment.courts.completedCases}</p>
          </div>
          <div>
            <p className="text-neutral-500">Общая сумма исков</p>
            <p className="text-neutral-900">{formatCurrency(enrichment.courts.totalAmount)}</p>
          </div>
        </div>
        {enrichment.courts.cases.length > 0 ? (
          <div className="border-t border-neutral-100 pt-4 mt-4">
            <p className="text-sm text-neutral-500 mb-2">История дел:</p>
            <div className="space-y-2">
              {enrichment.courts.cases.map((c, i) => (
                <div key={i} className="flex items-center justify-between text-sm bg-neutral-50 rounded-lg p-3">
                  <div>
                    <span className="text-neutral-900">{c.type}</span>
                    <span className="text-neutral-400 mx-2">•</span>
                    <span className="text-neutral-500">{c.date}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    {c.amount > 0 && (
                      <span className="text-neutral-900">{formatCurrency(c.amount)}</span>
                    )}
                    <span className="text-xs text-neutral-600">{c.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-neutral-500">Судебных дел не зафиксировано.</p>
        )}
        </>
        ) : (
          <p className="text-sm text-neutral-500">Нет данных</p>
        )}
      </div>

      {/* Risk / compliance */}
      <div className="bg-white rounded-xl border border-neutral-200 p-5">
        <SectionHeading
          icon={AlertTriangle}
          iconClassName="text-red-600"
          title="Факторы риска (riskFactor)"
          source={src('sanctions')}
        />
        {src('sanctions') === 'adata' &&
        ((enrichment.riskFlags?.length ?? 0) > 0 || enrichment.sanctions.isOnList) ? (
          <ul className="space-y-2">
            {(enrichment.riskFlags?.length
              ? enrichment.riskFlags
              : enrichment.sanctions.lists
            ).map((flag, i) => (
              <li
                key={i}
                className="text-sm text-red-800 bg-red-50 border border-red-100 rounded-lg px-3 py-2"
              >
                {flag}
              </li>
            ))}
          </ul>
        ) : src('sanctions') === 'adata' ? (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <p className="text-green-700">Критические факторы риска не выявлены</p>
          </div>
        ) : (
          <p className="text-sm text-neutral-500">Нет данных</p>
        )}
      </div>

      {((enrichment.contacts?.phones?.length ?? 0) > 0 ||
        (enrichment.contacts?.emails?.length ?? 0) > 0) && (
        <div className="bg-white rounded-xl border border-neutral-200 p-5">
          <SectionHeading
            icon={MessageSquare}
            iconClassName="text-neutral-600"
            title="Контакты (kzCoContact)"
            source={src('companyInfo')}
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            {(enrichment.contacts?.phones?.length ?? 0) > 0 && (
              <div>
                <p className="text-neutral-500 mb-1">Телефоны</p>
                <ul className="text-neutral-900 space-y-1">
                  {enrichment.contacts!.phones.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            )}
            {(enrichment.contacts?.emails?.length ?? 0) > 0 && (
              <div>
                <p className="text-neutral-500 mb-1">Email</p>
                <ul className="text-neutral-900 space-y-1">
                  {enrichment.contacts!.emails.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {enrichment.requisites && Object.keys(enrichment.requisites).length > 0 && (
        <div className="bg-white rounded-xl border border-neutral-200 p-5">
          <SectionHeading
            icon={FileText}
            iconClassName="text-neutral-600"
            title="Банковские реквизиты"
            source={src('companyInfo')}
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            {enrichment.requisites.iik && (
              <div>
                <p className="text-neutral-500">ИИК</p>
                <p className="font-mono text-neutral-900">{String(enrichment.requisites.iik)}</p>
              </div>
            )}
            {enrichment.requisites.bank && (
              <div>
                <p className="text-neutral-500">Банк</p>
                <p className="text-neutral-900">{String(enrichment.requisites.bank)}</p>
              </div>
            )}
            {enrichment.requisites.bik && (
              <div>
                <p className="text-neutral-500">БИК</p>
                <p className="font-mono text-neutral-900">{String(enrichment.requisites.bik)}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function DocumentsTab({ caseData }: { caseData: Case }) {
  const { addDocument } = useCases()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files) {
      Array.from(files).forEach((file) => {
        addDocument(caseData.id, file.name, file.type || 'application/octet-stream')
      })
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className="space-y-4">
      <div
        className="border-2 border-dashed border-neutral-300 rounded-xl p-8 text-center hover:border-neutral-400 transition-colors cursor-pointer"
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleFileSelect}
        />
        <Upload className="w-10 h-10 text-neutral-400 mx-auto mb-3" />
        <p className="text-neutral-600">Нажмите или перетащите файлы сюда</p>
        <p className="text-sm text-neutral-400 mt-1">Договоры, лицензии, сертификаты и др.</p>
      </div>

      {caseData.documents.length > 0 ? (
        <div className="bg-white rounded-xl border border-neutral-200 divide-y divide-neutral-100">
          {caseData.documents.map((doc) => (
            <div key={doc.id} className="flex items-center gap-3 p-4">
              <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <File className="w-5 h-5 text-blue-600" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-neutral-900 truncate">{doc.filename}</p>
                <p className="text-sm text-neutral-500">{doc.uploadedAt.toLocaleDateString('ru-RU')}</p>
              </div>
              <button className="p-2 hover:bg-neutral-100 rounded-lg transition-colors">
                <X className="w-4 h-4 text-neutral-400" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-center text-neutral-500 py-8">Документы пока не загружены</p>
      )}
    </div>
  )
}

function AssessmentTab({ caseData }: { caseData: Case }) {
  const { assessment, conclusion, dataSources } = caseData
  const assessmentSource = sectionSource(dataSources, 'assessment')
  const conclusionSource = sectionSource(dataSources, 'conclusion')

  if (!assessment) {
    return <LoadingGif message="Готовим оценку риска…" />
  }

  const riskConfig = {
    low: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', label: 'Низкий риск' },
    medium: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700', label: 'Средний риск' },
    high: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', label: 'Высокий риск' },
  }

  const config = riskConfig[assessment.riskLevel]

  return (
    <div className="space-y-6">
      {/* Risk Level */}
      <div className={`${config.bg} border ${config.border} rounded-xl p-6`}>
        <div className="flex items-center gap-3 mb-4">
          <div className={`w-12 h-12 rounded-full ${config.bg} border-2 ${config.border} flex items-center justify-center`}>
            <span className={`text-2xl font-bold ${config.text}`}>
              {assessment.riskLevel === 'low' ? 'L' : assessment.riskLevel === 'medium' ? 'M' : 'H'}
            </span>
          </div>
          <div>
            <p className={`text-lg font-semibold ${config.text}`}>{config.label}</p>
            <p className="text-sm text-neutral-500">
              Автоматическая оценка{' '}
              <span className="text-neutral-400">{dataSourceLabel(assessmentSource)}</span>
            </p>
          </div>
        </div>
        <p className="text-neutral-700">{assessment.summary}</p>
      </div>

      {/* Flags */}
      {assessment.flags.length > 0 && (
        <div className="bg-white rounded-xl border border-neutral-200 p-5">
          <h3 className="font-semibold text-neutral-900 mb-4">Выявленные факторы</h3>
          <div className="space-y-2">
            {assessment.flags.map((flag, i) => (
              <div
                key={i}
                className={`flex items-start gap-3 p-3 rounded-lg ${
                  flag.type === 'danger' ? 'bg-red-50' :
                  flag.type === 'warning' ? 'bg-amber-50' : 'bg-blue-50'
                }`}
              >
                <AlertTriangle className={`w-5 h-5 flex-shrink-0 ${
                  flag.type === 'danger' ? 'text-red-600' :
                  flag.type === 'warning' ? 'text-amber-600' : 'text-blue-600'
                }`} />
                <p className="text-sm text-neutral-700">{flag.message}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {conclusion ? (
        <div className="bg-white rounded-xl border border-neutral-200 p-5">
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <h3 className="font-semibold text-neutral-900">Заключение</h3>
            <span className="text-xs font-normal text-neutral-400">
              {dataSourceLabel(conclusionSource)}
            </span>
          </div>
          <MarkdownContent className="text-sm">{conclusion}</MarkdownContent>
        </div>
      ) : caseData.status === 'ready' ? (
        <div className="bg-white rounded-xl border border-neutral-200 p-5 flex items-center gap-3">
          <Loader2 className="w-5 h-5 text-neutral-400 animate-spin" />
          <p className="text-sm text-neutral-600">Генерация заключения ИИ…</p>
        </div>
      ) : null}

      {/* Recommendations */}
      <div className="bg-white rounded-xl border border-neutral-200 p-5">
        <h3 className="font-semibold text-neutral-900 mb-4">Рекомендации</h3>
        <ul className="space-y-2">
          {assessment.recommendations.map((rec, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-neutral-700">
              <span className="w-5 h-5 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center flex-shrink-0 text-xs font-medium">
                {i + 1}
              </span>
              {rec}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function ChatTab({ caseData }: { caseData: Case }) {
  const { addChatMessage } = useCases()
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [openaiReady, setOpenaiReady] = useState<boolean | null>(null)

  const hasData = Boolean(caseData.enrichment) && caseData.status === 'ready'

  useEffect(() => {
    fetchAiStatus()
      .then((s) => setOpenaiReady(s.openaiConfigured))
      .catch(() => setOpenaiReady(false))
  }, [])

  const handleSend = async () => {
    if (!input.trim() || isLoading || !hasData) return

    const text = input
    setInput('')
    setIsLoading(true)
    try {
      await addChatMessage(caseData.id, text)
    } finally {
      setIsLoading(false)
    }
  }

  const suggestions = [
    'Какие основные риски по этому контрагенту?',
    'Перечисли аффилированные компании и учредителей',
    'Есть ли налоговая задолженность и судебные дела?',
    'Составь служебную записку для согласования',
    'Какие документы запросить перед договором?',
  ]

  return (
    <div className="flex flex-col h-[600px]">
      {!hasData && (
        <div className="mb-4 text-sm text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-4 py-3">
          Дождитесь завершения проверки (статус «готово»), чтобы ИИ получил полное досье из Adata.
        </div>
      )}
      {openaiReady === false && hasData && (
        <div className="mb-4 text-sm text-neutral-600 bg-neutral-50 border border-neutral-200 rounded-lg px-4 py-3">
          OpenAI не подключён — ответы по шаблонам и фрагментам досье. Добавьте{' '}
          <code className="text-xs bg-neutral-100 px-1 rounded">OPENAI_API_KEY</code> в .env для
          полноценного диалога.
        </div>
      )}
      {openaiReady && hasData && (
        <div className="mb-4 text-sm text-emerald-800 bg-emerald-50 border border-emerald-100 rounded-lg px-4 py-3">
          ИИ видит все данные дела: компания, налоги, суды, риски, аффилиаты и заключение.
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-auto space-y-4 mb-4">
        {caseData.chatHistory.length === 0 ? (
          <div className="text-center py-12">
            <MessageSquare className="w-12 h-12 text-neutral-300 mx-auto mb-4" />
            <p className="text-neutral-500 mb-6">Задайте вопрос об этой компании</p>
            <div className="flex flex-wrap justify-center gap-2">
              {suggestions.map((s, i) => (
                <button
                  key={i}
                  onClick={() => setInput(s)}
                  className="px-3 py-1.5 bg-neutral-100 hover:bg-neutral-200 rounded-full text-sm text-neutral-700 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          caseData.chatHistory.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white border border-neutral-200 text-neutral-900'
                }`}
              >
                <MarkdownContent
                  className="text-sm"
                  inverted={msg.role === 'user'}
                >
                  {msg.content}
                </MarkdownContent>
              </div>
            </div>
          ))
        )}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-white border border-neutral-200 rounded-2xl px-4 py-3">
              <Loader2 className="w-5 h-5 text-neutral-400 animate-spin" />
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder={hasData ? 'Введите вопрос по контрагенту...' : 'Данные загружаются...'}
          disabled={!hasData}
          className="flex-1 px-4 py-3 border border-neutral-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-neutral-50"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || isLoading || !hasData}
          className="px-4 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send className="w-5 h-5" />
        </button>
      </div>
    </div>
  )
}

// ── Scoring Tab ───────────────────────────────────────────────────────────────

const METRIC_LABELS: Record<string, string> = {
  sanctions: 'Международные санкции',
  courts: 'Судебная активность',
  taxes: 'Налоговый комплаенс',
  legal_status: 'Правовой статус',
  pep: 'PEP-скрининг физлиц',
  adverse_media: 'Негативные публикации',
  affiliate_risk: 'Риск аффилиатов',
}

const METRIC_HINTS: Record<string, string> = {
  sanctions: 'LSEG WC1 + критические флаги КЗ (не налоговый риск)',
  courts: 'Судебные дела компании и руководителя (Adata)',
  taxes: 'Задолженность и степень налогового риска (Adata)',
  legal_status: 'Регистрация, ликвидация, финансовые проблемы',
  pep: 'Политически значимые лица (LSEG)',
  adverse_media: 'Негативные публикации (LSEG Media-Check)',
  affiliate_risk: 'Риск по дереву связей',
}

const SOURCE_BADGE: Record<string, { label: string; cls: string }> = {
  lseg: { label: 'LSEG WC1', cls: 'bg-purple-100 text-purple-700' },
  adata: { label: 'Adata', cls: 'bg-blue-100 text-blue-700' },
  affiliate_tree: { label: 'Аффилиаты', cls: 'bg-emerald-100 text-emerald-700' },
  none: { label: 'Нет данных', cls: 'bg-neutral-100 text-neutral-500' },
}

function ScoringTab({ caseData }: { caseData: Case }) {
  const breakdown: ScoreMetric[] = caseData.scoreBreakdown || []
  const totalScore = caseData.totalScore ?? null
  const lsegAt = caseData.lseg?.screenedAt

  if (breakdown.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-neutral-200 p-8 text-center">
        <TrendingUp className="w-10 h-10 text-neutral-300 mx-auto mb-3" />
        <p className="text-neutral-500 mb-2">Скоринг ещё не рассчитан</p>
        <p className="text-sm text-neutral-400">Дождитесь статуса «готово» или обновите проверку.</p>
      </div>
    )
  }

  const riskColor =
    caseData.riskLevel === 'high'
      ? 'text-red-600 bg-red-50 border-red-200'
      : caseData.riskLevel === 'medium'
        ? 'text-amber-600 bg-amber-50 border-amber-200'
        : 'text-emerald-600 bg-emerald-50 border-emerald-200'

  return (
    <div className="space-y-4">
      {/* Total score card */}
      <div className={`rounded-xl border p-5 ${riskColor}`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium opacity-70">Итоговый скоринг</p>
            <p className="text-4xl font-bold mt-1">
              {totalScore !== null ? totalScore.toFixed(1) : '—'}
              <span className="text-lg font-normal opacity-60"> / 100</span>
            </p>
          </div>
          <div className="text-right text-sm opacity-70">
            <p>Уровень риска</p>
            <p className="text-lg font-semibold capitalize mt-0.5">
              {caseData.riskLevel === 'high' ? 'Высокий' : caseData.riskLevel === 'medium' ? 'Средний' : 'Низкий'}
            </p>
          </div>
        </div>
        {lsegAt && (
          <p className="text-xs opacity-60 mt-3">
            LSEG WC1 скрининг: {new Date(lsegAt).toLocaleString('ru-RU')}
          </p>
        )}
      </div>

      {/* Metric breakdown */}
      <div className="bg-white rounded-xl border border-neutral-200 p-5 space-y-4">
        <h3 className="font-semibold text-neutral-900">Разбивка по метрикам</h3>
        {breakdown.map((m) => {
          const pct = m.max_points > 0 ? (m.points / m.max_points) * 100 : 0
          const barColor =
            pct >= 70
              ? 'bg-red-500'
              : pct >= 35
                ? 'bg-amber-500'
                : 'bg-emerald-500'
          const badge = SOURCE_BADGE[m.source] || SOURCE_BADGE.none
          return (
            <div key={m.metric}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-neutral-800">
                    {METRIC_LABELS[m.metric] || m.metric}
                  </span>
                  <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${badge.cls}`}>
                    {badge.label}
                  </span>
                </div>
                <span className="text-sm text-neutral-500">
                  {m.points.toFixed(1)} / {m.max_points}
                </span>
              </div>
              <div className="h-2 bg-neutral-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${barColor}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              {METRIC_HINTS[m.metric] && (
                <p className="text-xs text-neutral-400 mt-0.5">{METRIC_HINTS[m.metric]}</p>
              )}
              <p className="text-xs text-neutral-600 mt-1 leading-relaxed">{m.reason}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── LSEG Tab ──────────────────────────────────────────────────────────────────

const STRENGTH_CONFIG: Record<string, { cls: string; label: string }> = {
  EXACT:  { cls: 'bg-red-100 text-red-700 border border-red-200', label: 'EXACT' },
  STRONG: { cls: 'bg-orange-100 text-orange-700 border border-orange-200', label: 'STRONG' },
  MEDIUM: { cls: 'bg-amber-100 text-amber-700 border border-amber-200', label: 'MEDIUM' },
  WEAK:   { cls: 'bg-neutral-100 text-neutral-600 border border-neutral-200', label: 'WEAK' },
}

const CATEGORY_KEYWORDS = ['Special Interest', 'Interdicted', 'Sanctioned Entities', 'Sanctioned (50%']

const JURISDICTION_TAG_STYLES: Record<string, string> = {
  '🇺🇸 США': 'bg-red-100 text-red-700 border border-red-200',
  '🇬🇧 ВЕЛИКОБРИТАНИЯ': 'bg-amber-100 text-amber-700 border border-amber-200',
  '🇪🇺 ЕВРОСОЮЗ': 'bg-amber-100 text-amber-700 border border-amber-200',
  '🇰🇿 КАЗАХСТАН / СНГ': 'bg-sky-100 text-sky-700 border border-sky-200',
  '🌐 МЕЖДУНАРОДНЫЕ И ПРОЧИЕ': 'bg-neutral-100 text-neutral-700 border border-neutral-200',
  '🌐 КАТЕГОРИИ': 'bg-neutral-100 text-neutral-700 border border-neutral-200',
}

function groupSanctionsByJurisdiction(
  sanctionLists: string[],
  _rawSources?: string[],
): Record<string, string[]> {
  const groups: Record<string, string[]> = {}

  const JURISDICTION_MAP: [string, string, string[]][] = [
    ['🇺🇸 США', 'us', ['OFAC', 'BIS', 'SDN', 'SECON', 'CAATSA', 'Russia Specially Designated', 'Russia SDR']],
    ['🇬🇧 ВЕЛИКОБРИТАНИЯ', 'uk', ['UK HM Treasury', 'UKSANC', 'UKHMT']],
    ['🇪🇺 ЕВРОСОЮЗ', 'eu', ['EU', 'Russia Restrictive Measures', 'M:2C9']],
    ['🇰🇿 КАЗАХСТАН / СНГ', 'kz', ['KZKFM', 'KYSANC', 'KGFIU', 'UZDCEC', 'M:1UY']],
    ['🌐 МЕЖДУНАРОДНЫЕ И ПРОЧИЕ', 'intl', []],
  ]

  for (const list of sanctionLists || []) {
    let placed = false
    for (const [label, , keywords] of JURISDICTION_MAP.slice(0, -1)) {
      if (keywords.some((kw) => list.includes(kw))) {
        groups[label] = [...(groups[label] || []), list]
        placed = true
        break
      }
    }
    if (!placed) {
      const isCategory = CATEGORY_KEYWORDS.some((kw) => list.includes(kw))
      const intlLabel = isCategory ? '🌐 КАТЕГОРИИ' : '🌐 МЕЖДУНАРОДНЫЕ И ПРОЧИЕ'
      groups[intlLabel] = [...(groups[intlLabel] || []), list]
    }
  }
  return groups
}

function collectEntitySanctionLists(entity: LsegExtendedEntity): string[] {
  const lists = new Set<string>()
  for (const l of entity.sanctionLists || []) lists.add(l)
  for (const hit of entity.hits) {
    for (const l of hit.sanctionLists || hit.sourceCategories || []) lists.add(l)
  }
  return [...lists]
}

function collectAllSanctionLists(
  entities: LsegExtendedEntity[],
  lseg?: LsegData | null,
): string[] {
  const lists = new Set<string>()
  for (const e of entities.filter((x) => x.isOnSanctionList || x.hits.some((h) => h.isSanction))) {
    for (const l of collectEntitySanctionLists(e)) lists.add(l)
  }
  if (lseg?.sanctions?.isOnList || (lseg?.sanctions?.hits?.length ?? 0) > 0) {
    for (const l of lseg?.sanctions?.matchedLists || []) lists.add(l)
    for (const hit of lseg?.sanctions?.hits || []) {
      for (const l of hit.sanctionLists || hit.sourceCategories || []) lists.add(l)
    }
  }
  return [...lists]
}

function computeSanctionSummaryStats(
  entities: LsegExtendedEntity[],
  lseg?: LsegData | null,
) {
  const allLists = collectAllSanctionLists(entities, lseg)
  const has50Rule = allLists.some((l) => /50\s*%|50% Rule/i.test(l))

  const jurisdictionLabels: string[] = []
  const checks: [string, string[]][] = [
    ['США', ['OFAC', 'BIS', 'SDN', 'SECON', 'CAATSA', 'Russia Specially Designated', 'Russia SDR']],
    ['ЕС', ['EU', 'Russia Restrictive Measures', 'M:2C9']],
    ['UK', ['UK HM Treasury', 'UKSANC', 'UKHMT', 'UK 50%']],
    ['КЗ', ['KZKFM', 'KYSANC', 'KGFIU']],
    ['TR', ['TRMASAK']],
    ['UZ', ['UZDCEC']],
  ]
  for (const [label, keywords] of checks) {
    if (allLists.some((l) => keywords.some((kw) => l.includes(kw)))) {
      jurisdictionLabels.push(label)
    }
  }

  return {
    listCount: allLists.length,
    jurisdictionCount: jurisdictionLabels.length,
    jurisdictionLabels: jurisdictionLabels.join(', ') || '—',
    has50Rule,
  }
}

function uniqueSanctionListLabels(lists: string[]): string[] {
  return [...new Set((lists || []).map((l) => l.trim()).filter(Boolean))]
}

function JurisdictionSanctionGroups({ lists }: { lists: string[] }) {
  const groups = groupSanctionsByJurisdiction(uniqueSanctionListLabels(lists))
  const order = [
    '🇺🇸 США',
    '🇪🇺 ЕВРОСОЮЗ',
    '🇬🇧 ВЕЛИКОБРИТАНИЯ',
    '🇰🇿 КАЗАХСТАН / СНГ',
    '🌐 КАТЕГОРИИ',
    '🌐 МЕЖДУНАРОДНЫЕ И ПРОЧИЕ',
  ]

  return (
    <div className="space-y-4 mt-4">
      {order
        .filter((label) => (groups[label]?.length ?? 0) > 0)
        .map((label) => (
          <div key={label}>
            <p className="text-xs font-semibold text-neutral-600 uppercase tracking-wide mb-2">{label}</p>
            <div className="flex flex-wrap gap-1.5">
              {groups[label]!.map((tag, i) => (
                <span
                  key={i}
                  className={`text-xs px-2.5 py-1 rounded-full font-medium ${JURISDICTION_TAG_STYLES[label] || JURISDICTION_TAG_STYLES['🌐 МЕЖДУНАРОДНЫЕ И ПРОЧИЕ']}`}
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        ))}
    </div>
  )
}

function SanctionEntityCard({
  entity,
  isFocused,
  focusRef,
}: {
  entity: LsegExtendedEntity
  isFocused?: boolean
  focusRef?: RefObject<HTMLDivElement | null>
}) {
  const lists = collectEntitySanctionLists(entity)
  const isCritical = entity.isOnSanctionList

  return (
    <div
      ref={focusRef}
      className={`rounded-xl border p-5 ${
        isFocused
          ? 'ring-2 ring-blue-500 border-blue-300 bg-red-50'
          : isCritical
            ? 'bg-red-50 border-red-200'
            : 'bg-neutral-50 border-neutral-200'
      }`}
    >
      <div className="flex items-start justify-between gap-3 mb-1">
        <p className="text-base font-semibold text-neutral-900">{entity.name}</p>
        {isCritical && (
          <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full font-medium bg-red-100 text-red-700 border border-red-200 shrink-0">
            <AlertTriangle className="w-3 h-3" />
            Критический
          </span>
        )}
      </div>
      {entity.role && <p className="text-xs text-neutral-500 mb-1">{entity.role}</p>}
      {lists.length > 0 ? (
        <JurisdictionSanctionGroups lists={lists} />
      ) : (
        <p className="text-sm text-neutral-500 mt-3">Санкционные списки не указаны</p>
      )}
    </div>
  )
}

function SanctionSummaryHeader({
  sanctionedCount,
  stats,
}: {
  sanctionedCount: number
  stats: ReturnType<typeof computeSanctionSummaryStats>
}) {
  return (
    <div className="rounded-xl bg-white border border-neutral-200 overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-4 bg-red-600 text-white">
        <AlertTriangle className="w-5 h-5 shrink-0" />
        <p className="text-sm font-semibold">
          Критический риск — {sanctionedCount} аффилиат
          {sanctionedCount === 1 ? '' : sanctionedCount < 5 ? 'а' : 'ов'} под международными санкциями
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-neutral-200">
        <div className="px-5 py-4 bg-red-50">
          <p className="text-xs text-neutral-500 mb-1">Санкционных списков</p>
          <p className="text-2xl font-bold text-red-700">
            {stats.listCount >= 40 ? '40+' : stats.listCount || '—'}
          </p>
          {sanctionedCount > 0 && (
            <p className="text-xs text-neutral-500 mt-0.5">по {sanctionedCount} аффилиатам</p>
          )}
        </div>
        <div className="px-5 py-4 bg-neutral-50">
          <p className="text-xs text-neutral-500 mb-1">Юрисдикций</p>
          <p className="text-2xl font-bold text-neutral-900">{stats.jurisdictionCount || '—'}</p>
          <p className="text-xs text-neutral-500 mt-0.5">{stats.jurisdictionLabels}</p>
        </div>
        <div className="px-5 py-4 bg-neutral-50">
          <p className="text-xs text-neutral-500 mb-1">Правило 50%</p>
          <p className={`text-2xl font-bold ${stats.has50Rule ? 'text-amber-700' : 'text-neutral-400'}`}>
            {stats.has50Rule ? 'Да' : 'Нет'}
          </p>
          {stats.has50Rule && (
            <p className="text-xs text-neutral-500 mt-0.5">OFAC и UK HM Treasury</p>
          )}
        </div>
      </div>
    </div>
  )
}

function PepHitCard({ hit }: { hit: LsegSanctionHit }) {
  const strength = hit.matchStrength ? STRENGTH_CONFIG[hit.matchStrength] ?? STRENGTH_CONFIG.WEAK : null
  const lists = hit.sanctionLists && hit.sanctionLists.length > 0 ? hit.sanctionLists : hit.sourceCategories ?? []

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-neutral-900">
            {hit.submittedName || hit.primaryName || '—'}
          </p>
          {hit.primaryName && hit.primaryName !== hit.submittedName && (
            <p className="text-xs text-neutral-500 mt-0.5">WC1: {hit.primaryName}</p>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {strength && (
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${strength.cls}`}>
              {strength.label}
            </span>
          )}
          {hit.matchScore != null && (
            <span className="text-xs font-mono bg-amber-100 border border-amber-200 rounded px-1.5 py-0.5 text-amber-800">
              {hit.matchScore.toFixed(1)}%
            </span>
          )}
        </div>
      </div>
      {lists.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {lists.map((l, i) => (
            <span
              key={i}
              className="text-xs px-2 py-0.5 rounded-full font-medium bg-amber-100 text-amber-700 border border-amber-200"
            >
              {l}
            </span>
          ))}
        </div>
      )}
      {(hit.countryNames ?? []).length > 0 && (
        <p className="text-xs text-neutral-600">
          <span className="font-medium text-neutral-700">Страна: </span>
          {hit.countryNames!.join(', ')}
        </p>
      )}
      {(hit.aliases ?? []).length > 0 && (
        <p className="text-xs text-neutral-500">
          <span className="font-medium">Псевдонимы: </span>
          {hit.aliases!.join(' · ')}
        </p>
      )}
    </div>
  )
}

function LsegTab({ caseData, focusEntity }: { caseData: Case; focusEntity?: string | null }) {
  const lseg: LsegData | null | undefined = caseData.lseg
  const lsegExtended = caseData.lsegExtended
  const focusRef = useRef<HTMLDivElement>(null)
  const normalizedFocus = focusEntity?.trim().toLowerCase() ?? ''

  const sanctionedAffiliates: LsegExtendedEntity[] = lsegExtended
    ? Object.values(lsegExtended).filter((e) => e.isOnSanctionList)
    : []

  const allAffiliatesScreened: LsegExtendedEntity[] = lsegExtended
    ? Object.values(lsegExtended)
    : []

  useEffect(() => {
    if (!normalizedFocus || !focusRef.current) return
    focusRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [normalizedFocus, allAffiliatesScreened.length])

  if (!lseg && allAffiliatesScreened.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-neutral-200 p-8 text-center">
        <Globe className="w-10 h-10 text-neutral-300 mx-auto mb-3" />
        <p className="text-neutral-500 mb-2">LSEG World-Check One не запущен</p>
        <p className="text-sm text-neutral-400">
          Убедитесь, что LSEG_CLIENT_ID, LSEG_CLIENT_SECRET и LSEG_GROUP_ID настроены.
          Затем запустите повторную проверку.
        </p>
      </div>
    )
  }

  const riskBadge = (risk: string) => {
    if (risk === 'HIGH') return 'bg-red-100 text-red-700 border border-red-200'
    if (risk === 'MEDIUM') return 'bg-amber-100 text-amber-700 border border-amber-200'
    return 'bg-emerald-100 text-emerald-700 border border-emerald-200'
  }

  const summaryStats = computeSanctionSummaryStats(sanctionedAffiliates, lseg)
  const entitiesWithSanctions = allAffiliatesScreened.filter(
    (e) => e.isOnSanctionList || e.hits.some((h) => h.isSanction),
  )
  const cleanEntities = allAffiliatesScreened.filter(
    (e) => !e.isOnSanctionList && !e.hits.some((h) => h.isSanction || h.isPep),
  )
  const pepOnlyEntities = allAffiliatesScreened.filter(
    (e) => !e.isOnSanctionList && !e.hits.some((h) => h.isSanction) && e.hits.some((h) => h.isPep),
  )

  return (
    <div className="space-y-4">
      {sanctionedAffiliates.length > 0 && (
        <SanctionSummaryHeader
          sanctionedCount={sanctionedAffiliates.length}
          stats={summaryStats}
        />
      )}

      {entitiesWithSanctions.length > 0 && (
        <div className="space-y-4">
          {entitiesWithSanctions.map((entity, i) => {
            const isFocused =
              normalizedFocus.length > 0 &&
              entity.name.trim().toLowerCase() === normalizedFocus
            return (
              <SanctionEntityCard
                key={i}
                entity={entity}
                isFocused={isFocused}
                focusRef={isFocused ? focusRef : undefined}
              />
            )
          })}
        </div>
      )}

      {lseg && (
        <>
          <div className="rounded-xl bg-white border border-neutral-200 p-5">
            <div className="flex items-center gap-2 mb-3">
              <ShieldCheck className="w-5 h-5 text-purple-600" />
              <h3 className="font-semibold text-neutral-900">LSEG World-Check One</h3>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-neutral-500">Дата скрининга</p>
                <p className="font-medium text-neutral-900">
                  {new Date(lseg.screenedAt).toLocaleString('ru-RU')}
                </p>
              </div>
              <div>
                <p className="text-neutral-500">Рейтинг WC1</p>
                <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${riskBadge(lseg.wc1Rating)}`}>
                  {lseg.wc1Rating || 'N/A'}
                </span>
              </div>
            </div>
          </div>

          {(lseg.sanctions.isOnList ||
            lseg.sanctions.hasWatchlistHits ||
            (lseg.sanctions.hits ?? []).length > 0) && (
            <div className="rounded-xl bg-white border border-neutral-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-neutral-900">Санкционные списки (компания)</h3>
                <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${
                  lseg.sanctions.isOnList
                    ? 'bg-red-100 text-red-700 border border-red-200'
                    : 'bg-amber-100 text-amber-700 border border-amber-200'
                }`}>
                  {lseg.sanctions.isOnList
                    ? 'САНКЦИИ'
                    : (lseg.sanctions.hits ?? []).length > 0
                      ? 'ПРОВЕРИТЬ'
                      : 'ЧИСТО'}
                </span>
              </div>
              {/^бин\s*\d{12}$/i.test((lseg.screenedName || '').trim()) && (
                <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
                  Скрининг выполнялся по строке «{lseg.screenedName}», а не по юридическому названию —
                  WC1 мог подобрать посторонние совпадения по слову BIN. Перезапустите LSEG-скрининг
                  после обновления названия компании.
                </p>
              )}
              <JurisdictionSanctionGroups lists={lseg.sanctions.matchedLists || []} />
              {(lseg.sanctions.hits ?? []).length > 0 && (
                <div className="mt-4 space-y-2">
                  <p className="text-xs font-medium text-neutral-600">
                    Совпадения WC1 ({lseg.sanctions.hits.length})
                  </p>
                  {lseg.sanctions.hits.slice(0, 8).map((hit, i) => (
                    <PepHitCard key={hit.resultId || i} hit={hit} />
                  ))}
                  {lseg.sanctions.hits.length > 8 && (
                    <p className="text-xs text-neutral-500">
                      и ещё {lseg.sanctions.hits.length - 8} записей…
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {!lseg.sanctions.isOnList && (lseg.sanctions.hits ?? []).length === 0 && (
            <div className="rounded-xl bg-white border border-neutral-200 p-5">
              <p className="text-sm text-emerald-700">Совпадений в санкционных списках не обнаружено.</p>
            </div>
          )}

          <div className="rounded-xl bg-amber-50 border border-amber-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="font-semibold text-neutral-900">PEP-скрининг (физические лица)</h3>
                <p className="text-xs text-neutral-500 mt-0.5">Директор и руководство компании</p>
              </div>
              <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${
                lseg.pep.isHit
                  ? 'bg-amber-100 text-amber-700 border border-amber-200'
                  : 'bg-emerald-100 text-emerald-700 border border-emerald-200'
              }`}>
                {lseg.pep.isHit ? 'СОВПАДЕНИЕ' : 'Чисто'}
              </span>
            </div>
            {lseg.pep.isHit ? (
              <div className="space-y-3">
                {lseg.pep.individuals.map((ind, i) => (
                  <PepHitCard key={i} hit={ind} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-neutral-500">Связей с политически значимыми лицами не обнаружено.</p>
            )}
          </div>

          <div className="rounded-xl bg-white border border-neutral-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-neutral-900">Adverse Media</h3>
              {lseg.adverseMedia.negativeCount > 0 && (
                <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700 border border-amber-200">
                  {lseg.adverseMedia.negativeCount} негативных
                </span>
              )}
            </div>
            {lseg.adverseMedia.articles.length === 0 ? (
              <p className="text-sm text-neutral-500">Негативных публикаций не обнаружено.</p>
            ) : (
              <div className="space-y-2">
                {lseg.adverseMedia.articles.map((a) => (
                  <div key={a.articleId} className="flex items-start justify-between gap-3 p-3 rounded-lg bg-neutral-50 border border-neutral-200">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-neutral-900 line-clamp-2">{a.headline}</p>
                      <p className="text-xs text-neutral-500 mt-0.5">{a.publicationDate}</p>
                      {a.categories.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {a.categories.map((cat) => (
                            <span key={cat} className="text-xs bg-neutral-100 rounded px-1.5 py-0.5 text-neutral-600">{cat}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      {a.risk && (
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${riskBadge(a.risk)}`}>
                          {a.risk}
                        </span>
                      )}
                      {a.url && (
                        <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 hover:underline">
                          Источник →
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {pepOnlyEntities.length > 0 && (
        <div className="rounded-xl bg-amber-50 border border-amber-200 p-5 space-y-3">
          <h3 className="font-semibold text-neutral-900">PEP среди аффилиатов</h3>
          {pepOnlyEntities.map((entity, i) => (
            <div key={i}>
              <p className="text-sm font-medium text-neutral-800 mb-2">{entity.name}</p>
              {entity.hits.filter((h) => h.isPep).map((hit, j) => (
                <PepHitCard key={j} hit={hit} />
              ))}
            </div>
          ))}
        </div>
      )}

      {cleanEntities.length > 0 && (
        <div className="rounded-xl bg-white border border-neutral-200 p-5">
          <div className="flex items-center gap-2 mb-3">
            <Globe className="w-5 h-5 text-blue-600" />
            <h3 className="font-semibold text-neutral-900">Чистые аффилиаты ({cleanEntities.length})</h3>
          </div>
          <div className="space-y-2">
            {cleanEntities.map((entity, i) => (
              <div key={i} className="flex items-center justify-between text-sm py-2 border-b border-neutral-100 last:border-0">
                <span className="text-neutral-700">{entity.name}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 border border-emerald-200">
                  Чисто
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export function CaseDetail({ caseId }: { caseId: string }) {
  const searchParams = useSearchParams()
  const { getCase, refreshCase, apiConnected } = useCases()
  const [activeTab, setActiveTab] = useState<Tab>('data')
  const [focusEntity, setFocusEntity] = useState<string | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)
  const [loadingCase, setLoadingCase] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)

  const caseData = getCase(caseId)

  useEffect(() => {
    const tab = searchParams.get('tab')
    if (tab && VALID_TABS.includes(tab as Tab)) {
      setActiveTab(tab as Tab)
    }
    const entity = searchParams.get('entity')
    setFocusEntity(entity)
  }, [searchParams])

  useEffect(() => {
    if (caseData || !apiConnected) return

    let cancelled = false
    setLoadingCase(true)
    setLoadFailed(false)
    refreshCase(caseId)
      .then((row) => {
        if (!cancelled && !row) setLoadFailed(true)
      })
      .finally(() => {
        if (!cancelled) setLoadingCase(false)
      })

    return () => {
      cancelled = true
    }
  }, [caseId, caseData, apiConnected, refreshCase])

  if (loadingCase || (!caseData && apiConnected && !loadFailed)) {
    return <LoadingGif message="Загружаем дело…" />
  }

  if (!caseData) {
    return (
      <div className="text-center py-16">
        <p className="text-neutral-500">Дело не найдено</p>
      </div>
    )
  }

  const tabs: { id: Tab; label: string; icon: typeof Building2 }[] = [
    { id: 'data', label: 'Граф связей', icon: Network },
    { id: 'scoring', label: 'Скоринг', icon: TrendingUp },
    { id: 'lseg', label: 'LSEG / Санкции', icon: ShieldCheck },
    { id: 'documents', label: 'Документы', icon: FileText },
    { id: 'assessment', label: 'Заключение ИИ', icon: AlertTriangle },
    { id: 'chat', label: 'Чат с ИИ', icon: MessageSquare },
  ]

  const riskConfig = {
    low: { bg: 'bg-emerald-100', text: 'text-emerald-700', dot: 'bg-emerald-500' },
    medium: { bg: 'bg-amber-100', text: 'text-amber-700', dot: 'bg-amber-500' },
    high: { bg: 'bg-red-100', text: 'text-red-700', dot: 'bg-red-500' },
  }

  const risk = caseData.riskLevel ? riskConfig[caseData.riskLevel] : null
  const displayName = caseDisplayName(caseData)

  const handleDownloadReport = async () => {
    setReportError(null)
    setReportLoading(true)
    try {
      await downloadCaseReport(caseData.id, `adata-report-${caseData.iinBin}.pdf`)
    } catch (e) {
      setReportError(e instanceof Error ? e.message : 'Ошибка загрузки PDF')
    } finally {
      setReportLoading(false)
    }
  }

  return (
    <div>
      {/* Header */}
      <div className="bg-white rounded-xl border border-neutral-200 p-6 mb-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-semibold text-neutral-900">{displayName}</h1>
              {risk && (
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${risk.bg} ${risk.text}`}>
                  <span className={`w-2 h-2 rounded-full ${risk.dot}`} />
                  {caseData.riskLevel === 'low' ? 'Низкий риск' : caseData.riskLevel === 'medium' ? 'Средний риск' : 'Высокий риск'}
                </span>
              )}
              {caseData.totalScore !== null && caseData.totalScore !== undefined && (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-neutral-100 text-neutral-600">
                  <TrendingUp className="w-3 h-3" />
                  {caseData.totalScore.toFixed(1)} / 100
                </span>
              )}
              {caseData.lseg && (() => {
                const extEntities = caseData.lsegExtended ? Object.values(caseData.lsegExtended) : []
                const hasSanctionedAffiliate = extEntities.some(e => e.isOnSanctionList)
                return hasSanctionedAffiliate ? (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-red-600 text-white">
                    <AlertTriangle className="w-3 h-3" />
                    САНКЦИИ АФФИЛИАТ
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-700">
                    <ShieldCheck className="w-3 h-3" />
                    LSEG WC1
                  </span>
                )
              })()}
            </div>
            <p className="text-neutral-500">
              <span className="font-mono">{caseData.iinBin}</span>
              <span className="mx-2">•</span>
              <span>Добавлено {caseData.createdAt.toLocaleDateString('ru-RU')}</span>
            </p>
            {reportError && (
              <p className="text-sm text-red-600 mt-2">{reportError}</p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Link
              href={`/cases/${caseData.id}/full-report`}
              className="flex items-center gap-2 px-4 py-2.5 bg-red-50 hover:bg-red-100 text-red-800 border border-red-200 text-sm font-medium rounded-lg transition-colors"
            >
              <FileText className="w-4 h-4" />
              Полный отчёт
            </Link>
            <Link
              href={`/cases/${caseData.id}/report`}
              className="flex items-center gap-2 px-4 py-2.5 bg-neutral-100 hover:bg-neutral-200 text-neutral-700 text-sm font-medium rounded-lg transition-colors"
            >
              <FileText className="w-4 h-4" />
              Отчёт PDF
            </Link>
            <button
              type="button"
              onClick={handleDownloadReport}
              disabled={reportLoading}
              className="flex items-center gap-2 px-4 py-2.5 bg-neutral-900 hover:bg-neutral-800 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {reportLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Download className="w-4 h-4" />
              )}
              PDF Adata
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
        {tabs.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium text-sm whitespace-nowrap transition-colors ${
                activeTab === tab.id
                  ? 'bg-blue-600 text-white'
                  : 'bg-white border border-neutral-200 text-neutral-600 hover:bg-neutral-50'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab content */}
      {activeTab === 'data' && (
        <DataTab caseData={caseData} onRefresh={() => refreshCase(caseId)} />
      )}
      {activeTab === 'scoring' && <ScoringTab caseData={caseData} />}
      {activeTab === 'lseg' && <LsegTab caseData={caseData} focusEntity={focusEntity} />}
      {activeTab === 'documents' && <DocumentsTab caseData={caseData} />}
      {activeTab === 'assessment' && <AssessmentTab caseData={caseData} />}
      {activeTab === 'chat' && <ChatTab caseData={caseData} />}
    </div>
  )
}
