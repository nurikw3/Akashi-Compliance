'use client'

import { useState, useRef, useEffect } from 'react'
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
} from 'lucide-react'
import { downloadCaseReport, fetchAiStatus } from '@/lib/api'
import { useCases } from '@/lib/cases-context'
import { AffiliatesGraph } from '@/components/affiliates-graph'
import { MarkdownContent } from '@/components/markdown-content'
import { dataSourceLabel, sectionSource } from '@/lib/data-source-label'
import type { Case, DataSourceKind } from '@/lib/types'

type Tab = 'data' | 'documents' | 'assessment' | 'chat'

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
  const src = (section: Parameters<typeof sectionSource>[1]) =>
    sectionSource(dataSources, section)

  if (!enrichment) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-8 h-8 text-neutral-400 animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Affiliates Graph - Main Feature */}
      <AffiliatesGraph
        caseId={caseData.id}
        mainCompany={{ name: caseData.name, iinBin: caseData.iinBin }}
        affiliateTree={caseData.affiliateTree}
        source={src('graph')}
        onTreeUpdated={onRefresh}
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
            <p className="text-neutral-900">{enrichment.companyInfo.director}</p>
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
        {src('courts') === 'stub' ? (
          <p className="text-sm text-neutral-500">Данные из Adata не получены.</p>
        ) : (
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
        {src('sanctions') === 'stub' ? (
          <p className="text-sm text-neutral-500">Данные из Adata не получены.</p>
        ) : (enrichment.riskFlags?.length ?? 0) > 0 || enrichment.sanctions.isOnList ? (
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
        ) : (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <p className="text-green-700">Критические факторы риска не выявлены</p>
          </div>
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
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-8 h-8 text-neutral-400 animate-spin" />
      </div>
    )
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

export function CaseDetail({ caseId }: { caseId: string }) {
  const { getCase, refreshCase, apiConnected } = useCases()
  const [activeTab, setActiveTab] = useState<Tab>('data')
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)
  const [loadingCase, setLoadingCase] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)

  const caseData = getCase(caseId)

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
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-8 h-8 text-neutral-400 animate-spin" />
      </div>
    )
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
              <h1 className="text-2xl font-semibold text-neutral-900">{caseData.name}</h1>
              {risk && (
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${risk.bg} ${risk.text}`}>
                  <span className={`w-2 h-2 rounded-full ${risk.dot}`} />
                  {caseData.riskLevel === 'low' ? 'Низкий риск' : caseData.riskLevel === 'medium' ? 'Средний риск' : 'Высокий риск'}
                </span>
              )}
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
          <button
            type="button"
            onClick={handleDownloadReport}
            disabled={reportLoading}
            className="flex items-center gap-2 px-4 py-2.5 bg-neutral-900 hover:bg-neutral-800 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors shrink-0"
          >
            {reportLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Download className="w-4 h-4" />
            )}
            PDF отчёт Adata
          </button>
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
      {activeTab === 'documents' && <DocumentsTab caseData={caseData} />}
      {activeTab === 'assessment' && <AssessmentTab caseData={caseData} />}
      {activeTab === 'chat' && <ChatTab caseData={caseData} />}
    </div>
  )
}
