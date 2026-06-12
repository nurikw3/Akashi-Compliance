'use client'

import { useState, useRef, useEffect, type ReactNode, type RefObject } from 'react'
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
  Info,
  Globe,
  ListChecks,
  ChevronDown,
  ChevronRight,
  Database,
  Sparkles,
} from 'lucide-react'
import { downloadCaseReport, downloadDossier, downloadSanctionsSummary, fetchAiStatus, rescreenAllWithLseg } from '@/lib/api'
import { useCases } from '@/lib/cases-context'
import { AffiliatesGraph } from '@/components/affiliates-graph'
import { LoadingGif } from '@/components/loading-gif'
import { MarkdownContent } from '@/components/markdown-content'
import { dataSourceLabel, sectionSource } from '@/lib/data-source-label'
import { resolveSectionSource } from '@/lib/source-ref'
import { Abbr } from '@/components/ui/abbr'
import { SourceRef } from '@/components/ui/source-ref'
import { caseDisplayName, formatPersonField, pdfFileName } from '@/lib/case-display'
import type { Case, DataSourceKind, DataSources, LsegData, LsegSanctionHit, LsegExtendedEntity, IndividualCourtCase, VerificationLogEvent, OsintData, OsintFinding, OsintCategory } from '@/lib/types'

type Tab = 'data' | 'documents' | 'assessment' | 'chat' | 'lseg' | 'osint' | 'log'

const VALID_TABS: Tab[] = ['data', 'documents', 'assessment', 'chat', 'lseg', 'osint', 'log']

function SectionHeading({
  icon: Icon,
  iconClassName,
  title,
  source,
  dataSources,
  verificationLog,
  sectionKey,
}: {
  icon: typeof Building2
  iconClassName: string
  title: ReactNode
  source: DataSourceKind
  dataSources?: DataSources
  verificationLog?: VerificationLogEvent[]
  sectionKey?: keyof DataSources
}) {
  return (
    <div className="flex items-center gap-2 mb-4 flex-wrap">
      <Icon className={`w-5 h-5 ${iconClassName}`} />
      <h3 className="font-semibold text-neutral-900">{title}</h3>
      {sectionKey && (
        <SourceRef source={resolveSectionSource(dataSources, verificationLog, sectionKey)} />
      )}
    </div>
  )
}

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('ru-RU').format(amount) + ' тг'
}

type CourtsTab = 'company' | 'personal'

function DetailedCourtCasesList({
  cases,
  keyPrefix,
  expandedCases,
  onToggleCase,
}: {
  cases: IndividualCourtCase[]
  keyPrefix: string
  expandedCases: Set<string>
  onToggleCase: (key: string) => void
}) {
  if (!cases.length) return null

  return (
    <div className="space-y-3 mt-4">
      {cases.map((courtCase, idx) => {
        const caseKey = `${keyPrefix}-${courtCase.number || idx}`
        const isExpanded = expandedCases.has(caseKey)
        const hasDetails =
          (courtCase.history?.length ?? 0) > 0 || (courtCase.documents?.length ?? 0) > 0
        return (
          <div
            key={caseKey}
            className="bg-neutral-50 rounded-lg border border-neutral-100 overflow-hidden"
          >
            <button
              type="button"
              onClick={() => onToggleCase(caseKey)}
              className="w-full flex items-start gap-2 p-3 text-left hover:bg-neutral-100/80 transition-colors"
            >
              {hasDetails ? (
                isExpanded ? (
                  <ChevronDown className="w-4 h-4 mt-0.5 shrink-0 text-neutral-400" />
                ) : (
                  <ChevronRight className="w-4 h-4 mt-0.5 shrink-0 text-neutral-400" />
                )
              ) : (
                <span className="w-4 h-4 shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                  <span className="font-medium text-neutral-900">{courtCase.number || '—'}</span>
                  <span className="text-neutral-400">•</span>
                  <span className="text-neutral-700">{courtCase.type || '—'}</span>
                  {courtCase.role && (
                    <>
                      <span className="text-neutral-400">•</span>
                      <span className="text-neutral-600">{courtCase.role}</span>
                    </>
                  )}
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-neutral-500 mt-1">
                  <span>{courtCase.court || '—'}</span>
                  <span>{courtCase.date || '—'}</span>
                  {courtCase.category && <span>{courtCase.category}</span>}
                  {courtCase.result && (
                    <span className="text-neutral-700">{courtCase.result}</span>
                  )}
                </div>
              </div>
            </button>
            {isExpanded && hasDetails && (
              <div className="px-3 pb-3 pt-0 ml-6 border-t border-neutral-100">
                {(courtCase.documents?.length ?? 0) > 0 && (
                  <div className="mt-3 mb-4">
                    <p className="text-xs text-neutral-500 mb-2">Документы по делу</p>
                    <div className="flex flex-wrap gap-3">
                      {courtCase.documents!.map((doc, docIdx) => (
                        <a
                          key={docIdx}
                          href={doc.doc_link ?? '#'}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline text-sm"
                        >
                          📄 {doc.file_name || 'Документ'}
                        </a>
                      ))}
                    </div>
                  </div>
                )}
                {(courtCase.history?.length ?? 0) > 0 && (
                  <>
                    <p className="text-xs text-neutral-500 mt-3 mb-2">История событий</p>
                    <div className="space-y-2">
                      {courtCase.history!.map((event, eventIdx) => (
                        <div
                          key={eventIdx}
                          className="text-sm bg-white rounded-md border border-neutral-100 p-2.5"
                        >
                          <div className="flex flex-wrap gap-x-2 text-neutral-700">
                            <span className="text-neutral-500">{event.event_date}</span>
                            <span>{event.name}</span>
                          </div>
                          {(event.documents?.length ?? 0) > 0 && (
                            <div className="mt-2 flex flex-wrap gap-3">
                              {event.documents!.map((doc, docIdx) => (
                                <a
                                  key={docIdx}
                                  href={doc.doc_link}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-blue-600 hover:underline text-sm"
                                >
                                  📄 {doc.file_name}
                                </a>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function PersonalCourtsPanel({ caseData }: { caseData: Case }) {
  const [expandedCases, setExpandedCases] = useState<Set<string>>(new Set())
  const individualCourts = caseData.individualCourts
  const individualCourtsMeta = caseData.individualCourtsMeta ?? {}
  const entries = individualCourts ? Object.entries(individualCourts) : []
  const hasData = entries.some(([, cases]) => (cases?.length ?? 0) > 0)
  const directorIin =
    caseData.enrichment?.companyInfo?.director_iin ??
    Object.keys(individualCourtsMeta)[0] ??
    null

  const toggleCase = (key: string) => {
    setExpandedCases((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  if (!hasData) {
    if (caseData.deepDiveStatus === 'pending') {
      return <LoadingGif message="Загружаем судебные дела связанных лиц…" size={120} className="py-8" />
    }
    return (
      <p className="text-sm text-neutral-500">
        {directorIin
          ? `Персональные судебные дела не найдены (ИИН ${directorIin})`
          : 'Персональные судебные дела не найдены (ИИН директора недоступен)'}
      </p>
    )
  }

  return (
    <div className="space-y-6">
      {entries.map(([iin, cases]) => {
        if (!cases?.length) return null
        const meta = individualCourtsMeta[iin]
        const personName = meta?.name || `ИИН ${iin}`
        return (
          <div key={iin} className="border border-neutral-100 rounded-lg p-4">
            <div className="mb-4">
              <p className="font-medium text-neutral-900">{personName}</p>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-neutral-500 mt-1">
                <span className="font-mono">ИИН: {iin}</span>
                {meta?.role && <span>{meta.role}</span>}
              </div>
              {(meta?.companyName || meta?.companyBin) && (
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-sm text-neutral-700 mt-1.5 bg-neutral-50 rounded-md px-3 py-1.5 border border-neutral-100">
                  {meta.companyName && <span className="font-medium">{meta.companyName}</span>}
                  {meta.companyBin && <span className="font-mono text-neutral-500">БИН: {meta.companyBin}</span>}
                </div>
              )}
            </div>
            <DetailedCourtCasesList
              cases={cases}
              keyPrefix={iin}
              expandedCases={expandedCases}
              onToggleCase={toggleCase}
            />
          </div>
        )
      })}
    </div>
  )
}

function CourtsSection({
  caseData,
  courtsSource,
}: {
  caseData: Case
  courtsSource: DataSourceKind
}) {
  const [tab, setTab] = useState<CourtsTab>('company')
  const [expandedCompanyCases, setExpandedCompanyCases] = useState<Set<string>>(new Set())
  const enrichment = caseData.enrichment
  const courts = enrichment?.courts
  const companyCourtCases = caseData.companyCourtCases ?? []
  const companyHasData =
    courtsSource === 'adata' ||
    (courts?.activeCases ?? 0) > 0 ||
    (courts?.completedCases ?? 0) > 0 ||
    (courts?.totalAmount ?? 0) > 0 ||
    companyCourtCases.length > 0

  const toggleCompanyCase = (key: string) => {
    setExpandedCompanyCases((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  return (
    <div className="bg-white rounded-xl border border-neutral-200 p-5">
      <SectionHeading
        icon={Gavel}
        iconClassName="text-amber-600"
        title="Судебные дела"
        source={courtsSource}
        dataSources={caseData.dataSources}
        verificationLog={caseData.verificationLog}
        sectionKey="courts"
      />
      <div className="flex flex-wrap gap-2 mb-4">
        <button
          type="button"
          onClick={() => setTab('company')}
          className={`text-sm px-3 py-1.5 rounded-lg border transition-colors ${
            tab === 'company'
              ? 'bg-neutral-900 text-white border-neutral-900'
              : 'bg-white text-neutral-700 border-neutral-200 hover:border-neutral-300'
          }`}
        >
          Компания
          {caseData.iinBin ? (
            <span className="ml-1.5 font-mono text-xs opacity-80">({caseData.iinBin})</span>
          ) : null}
        </button>
        <button
          type="button"
          onClick={() => setTab('personal')}
          className={`text-sm px-3 py-1.5 rounded-lg border transition-colors ${
            tab === 'personal'
              ? 'bg-neutral-900 text-white border-neutral-900'
              : 'bg-white text-neutral-700 border-neutral-200 hover:border-neutral-300'
          }`}
        >
          Персональные
        </button>
      </div>

      {tab === 'company' ? (
        companyHasData && courts ? (
          <>
            {courts.note && (
              <p className="text-sm text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 mb-4">
                {courts.note}
              </p>
            )}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-neutral-500">Активные дела</p>
                <p className="text-neutral-900 font-medium">{courts.activeCases}</p>
              </div>
              <div>
                <p className="text-neutral-500">Завершенные дела</p>
                <p className="text-neutral-900">{courts.completedCases}</p>
              </div>
              <div>
                <p className="text-neutral-500">Общая сумма исков</p>
                <p className="text-neutral-900">{formatCurrency(courts.totalAmount)}</p>
              </div>
            </div>
            {companyCourtCases.length > 0 && (
              <>
                <p className="text-sm text-neutral-600 mt-6 mb-1">
                  Детальные дела ({companyCourtCases.length})
                </p>
                <DetailedCourtCasesList
                  cases={companyCourtCases}
                  keyPrefix={caseData.iinBin || 'company'}
                  expandedCases={expandedCompanyCases}
                  onToggleCase={toggleCompanyCase}
                />
              </>
            )}
          </>
        ) : (
          <p className="text-sm text-neutral-500">Нет данных по компании</p>
        )
      ) : (
        <PersonalCourtsPanel caseData={caseData} />
      )}
    </div>
  )
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
          dataSources={dataSources}
          verificationLog={caseData.verificationLog}
          sectionKey="companyInfo"
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
              <p className="text-neutral-500">Статус (<Abbr code="Adata">Adata</Abbr>)</p>
              <p className="text-neutral-900 capitalize">{enrichment.companyInfo.operatingStatus}</p>
            </div>
          )}
          {enrichment.companyInfo.legalForm && (
            <div>
              <p className="text-neutral-500"><Abbr code="ОПФ">ОПФ</Abbr></p>
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
              <p className="text-neutral-500">Карточка <Abbr code="Adata">Adata</Abbr></p>
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
            dataSources={dataSources}
            verificationLog={caseData.verificationLog}
            sectionKey="companyInfo"
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
          dataSources={dataSources}
          verificationLog={caseData.verificationLog}
          sectionKey="taxes"
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

      <CourtsSection caseData={caseData} courtsSource={src('courts')} />

      {/* Risk / compliance */}
      <div className="bg-white rounded-xl border border-neutral-200 p-5">
        <SectionHeading
          icon={AlertTriangle}
          iconClassName="text-red-600"
          title="Факторы риска (riskFactor)"
          source={src('sanctions')}
          dataSources={dataSources}
          verificationLog={caseData.verificationLog}
          sectionKey="sanctions"
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
            <p className="text-green-700">Факторы (riskFactor) в источнике не указаны</p>
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
            dataSources={dataSources}
            verificationLog={caseData.verificationLog}
            sectionKey="companyInfo"
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
            dataSources={dataSources}
            verificationLog={caseData.verificationLog}
            sectionKey="companyInfo"
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
    return <LoadingGif message="Готовим заключение…" />
  }

  return (
    <div className="space-y-6">
      {/* Findings */}
      {assessment.flags.length > 0 && (
        <div className="bg-white rounded-xl border border-neutral-200 p-5">
          <div className="flex items-center gap-2 mb-4 flex-wrap">
            <h3 className="font-semibold text-neutral-900">Выявленные факторы</h3>
            <span className="text-xs font-normal text-neutral-400">
              {dataSourceLabel(assessmentSource)}
            </span>
          </div>
          <div className="space-y-2">
            {assessment.flags.map((flag, i) => (
              <div
                key={i}
                className="flex items-start gap-3 p-3 rounded-lg bg-neutral-50"
              >
                <Info className="w-5 h-5 flex-shrink-0 text-neutral-400" />
                <p className="text-sm text-neutral-700">
                  {flag.message}
                  <SourceRef provider="Adata" />
                </p>
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

  const [showSuggestions, setShowSuggestions] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [caseData.chatHistory, isLoading])

  const suggestionGroups = [
    {
      label: '🎯 Решение',
      items: [
        'Можно ли подписывать договор с этой компанией? Дай чёткий вывод.',
        'Составь служебную записку для согласования сделки на 50 млн тг',
      ],
    },
    {
      label: '🕸️ Сеть и аффилиаты',
      items: [
        'Обойди граф аффилиатов — есть ли проблемы в группе компаний?',
        'В каких ещё компаниях директор этой компании является руководителем?',
        'Сравни эту компанию с её основным аффилиатом',
      ],
    },
    {
      label: '⚖️ Суды',
      items: [
        'Какие судебные дела у директора? Есть ли красные флаги для сделки?',
        'Директор выступает ответчиком по каким статьям?',
      ],
    },
    {
      label: '🛡️ Санкции',
      items: [
        'Есть ли санкции у компании или её аффилиатов?',
        'Кто из связанных лиц попал в санкционные списки LSEG?',
      ],
    },
    {
      label: '📋 Документы',
      items: [
        'Какие документы запросить у контрагента перед подписанием договора?',
      ],
    },
  ]

  const handleSuggest = (s: string) => {
    setInput(s)
    setShowSuggestions(false)
  }

  return (
    <div className="flex flex-col h-[600px]">
      {!hasData && (
        <div className="mb-4 text-sm text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-4 py-3">
          Дождитесь завершения проверки (статус «готово»), чтобы ИИ получил полное досье.
        </div>
      )}
      {openaiReady === false && hasData && (
        <div className="mb-3 text-sm text-neutral-600 bg-neutral-50 border border-neutral-200 rounded-lg px-4 py-3">
          OpenAI не подключён — ответы по шаблонам.{' '}
          <code className="text-xs bg-neutral-100 px-1 rounded">OPENAI_API_KEY</code> → полный диалог.
        </div>
      )}
      {openaiReady && hasData && (
        <div className="mb-3 text-sm text-emerald-800 bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2">
          ИИ видит данные дела: суды, санкции, аффилиаты, скоринг.
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-auto space-y-3 mb-3 pr-1">
        {caseData.chatHistory.length === 0 ? (
          <div className="py-8 space-y-5">
            <div className="text-center">
              <MessageSquare className="w-10 h-10 text-neutral-300 mx-auto mb-3" />
              <p className="text-neutral-500 text-sm">Задайте вопрос об этой компании</p>
            </div>
            {suggestionGroups.map((group) => (
              <div key={group.label}>
                <p className="text-xs font-semibold text-neutral-400 uppercase tracking-wide mb-2 px-1">
                  {group.label}
                </p>
                <div className="flex flex-col gap-1.5">
                  {group.items.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => handleSuggest(s)}
                      className="text-left px-3 py-2 bg-neutral-50 hover:bg-neutral-100 border border-neutral-200 rounded-lg text-sm text-neutral-700 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <>
            {caseData.chatHistory.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[82%] rounded-2xl px-4 py-3 ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-white border border-neutral-200 text-neutral-900'
                  }`}
                >
                  <MarkdownContent className="text-sm" inverted={msg.role === 'user'}>
                    {msg.content}
                  </MarkdownContent>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-white border border-neutral-200 rounded-2xl px-4 py-3">
                  <Loader2 className="w-4 h-4 text-neutral-400 animate-spin" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Quick suggestions dropdown */}
      {showSuggestions && caseData.chatHistory.length > 0 && (
        <div className="mb-2 border border-neutral-200 rounded-xl bg-white shadow-sm overflow-hidden max-h-64 overflow-y-auto">
          {suggestionGroups.map((group) => (
            <div key={group.label} className="border-b border-neutral-100 last:border-0">
              <p className="text-[10px] font-semibold text-neutral-400 uppercase tracking-wide px-3 pt-2 pb-1">
                {group.label}
              </p>
              {group.items.map((s, i) => (
                <button
                  key={i}
                  onClick={() => handleSuggest(s)}
                  className="w-full text-left px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-50 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="flex gap-2 items-center">
        {caseData.chatHistory.length > 0 && (
          <button
            onClick={() => setShowSuggestions((v) => !v)}
            title="Шаблоны вопросов"
            className="p-3 border border-neutral-200 rounded-xl text-neutral-500 hover:bg-neutral-50 transition-colors"
          >
            <Sparkles className="w-4 h-4" />
          </button>
        )}
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder={hasData ? 'Введите вопрос...' : 'Данные загружаются...'}
          disabled={!hasData}
          className="flex-1 px-4 py-3 border border-neutral-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-neutral-50 text-sm"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || isLoading || !hasData}
          className="px-4 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send className="w-4 h-4" />
        </button>
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
            Под санкциями
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
          Санкционные аффилиаты: {sanctionedCount} аффилиат
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
            <p className="text-xs text-neutral-500 mt-0.5"><Abbr code="WC1">WC1</Abbr>: {hit.primaryName}</p>
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

// ─── OSINT (open-source intelligence) ─────────────────────────────────────

const OSINT_CATEGORY_META: Record<OsintCategory, { label: string; accent: string }> = {
  sanctions: { label: 'Санкции', accent: 'text-red-700' },
  corruption: { label: 'Коррупция', accent: 'text-orange-700' },
  reputation: { label: 'Репутационные риски', accent: 'text-amber-700' },
  conflict_of_interest: { label: 'Конфликт интересов', accent: 'text-purple-700' },
}

const OSINT_ROLE_LABEL: Record<OsintFinding['subjectRole'], string> = {
  company: 'Компания',
  director: 'Директор',
  founder: 'Учредитель',
}

function OsintFindingCard({ finding }: { finding: OsintFinding }) {
  return (
    <div className="p-3 rounded-lg bg-neutral-50 border border-neutral-200">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-xs px-2 py-0.5 rounded-full bg-neutral-200 text-neutral-700">
              {OSINT_ROLE_LABEL[finding.subjectRole] ?? finding.subjectRole}
            </span>
            {finding.subject && (
              <span className="text-xs text-neutral-500 truncate">{finding.subject}</span>
            )}
          </div>
          <p className="text-sm font-medium text-neutral-900">{finding.title}</p>
          {finding.summary && (
            <p className="text-sm text-neutral-600 mt-0.5">{finding.summary}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {finding.publishedDate && (
            <span className="text-xs text-neutral-400">{finding.publishedDate}</span>
          )}
          <a
            href={finding.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:underline"
          >
            {finding.sourceName || 'источник'} ↗
          </a>
        </div>
      </div>
    </div>
  )
}

function OsintTab({ caseData }: { caseData: Case }) {
  const osint: OsintData | null | undefined = caseData.osint
  const status = caseData.osintStatus

  if (!osint && status === 'pending') {
    return (
      <div className="rounded-xl bg-white border border-neutral-200">
        <LoadingGif
          message="Ищем упоминания в открытых источниках…"
          size={120}
          className="py-8"
        />
      </div>
    )
  }

  if (!osint) {
    return (
      <div className="bg-white rounded-xl border border-neutral-200 p-8 text-center">
        <Globe className="w-10 h-10 text-neutral-300 mx-auto mb-3" />
        <p className="text-neutral-500 mb-2">
          {status === 'error'
            ? 'Поиск по открытым источникам не выполнен'
            : 'OSINT-поиск не запущен'}
        </p>
        <p className="text-sm text-neutral-400">
          Модуль ищет санкции, коррупцию, репутационные риски и конфликт интересов
          в открытых источниках — в дополнение к LSEG и A-Data.
        </p>
      </div>
    )
  }

  const categories: OsintCategory[] = [
    'sanctions',
    'corruption',
    'reputation',
    'conflict_of_interest',
  ]
  const total = osint.findings.length

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-white border border-neutral-200 p-5">
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <Globe className="w-5 h-5 text-blue-600" />
          <h3 className="font-semibold text-neutral-900">Открытые источники (OSINT)</h3>
          <SourceRef provider="OSINT" />
        </div>
        <p className="text-sm text-neutral-500">
          Дополнение к LSEG и A-Data: только новые упоминания, не найденные в этих
          источниках.
          {osint.screenedAt && (
            <> Проверено {new Date(osint.screenedAt).toLocaleString('ru-RU')}.</>
          )}
        </p>
        {total === 0 && (
          <p className="text-sm text-emerald-700 mt-2">
            Дополнительных упоминаний в открытых источниках не обнаружено.
          </p>
        )}
        {osint.sources.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {osint.sources.slice(0, 12).map((s) => (
              <span
                key={s}
                className="text-xs bg-neutral-100 rounded px-1.5 py-0.5 text-neutral-600"
              >
                {s}
              </span>
            ))}
          </div>
        )}
      </div>

      {categories.map((cat) => {
        const items = osint.findings.filter((f) => f.category === cat)
        const meta = OSINT_CATEGORY_META[cat]
        return (
          <div key={cat} className="rounded-xl bg-white border border-neutral-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className={`font-semibold ${meta.accent}`}>{meta.label}</h3>
              <span className="text-xs px-2 py-0.5 rounded-full bg-neutral-100 text-neutral-600">
                {items.length}
              </span>
            </div>
            {items.length === 0 ? (
              <p className="text-sm text-neutral-400">Не выявлено</p>
            ) : (
              <div className="space-y-2">
                {items.map((f, i) => (
                  <OsintFindingCard key={`${f.sourceUrl}-${i}`} finding={f} />
                ))}
              </div>
            )}
          </div>
        )
      })}
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
            <div className="flex items-center gap-2 mb-3 flex-wrap">
              <ShieldCheck className="w-5 h-5 text-purple-600" />
              <h3 className="font-semibold text-neutral-900">
                <Abbr code="LSEG">LSEG</Abbr> World-Check One
              </h3>
              <SourceRef provider="LSEG" />
              <button
                onClick={() =>
                  downloadSanctionsSummary(
                    caseData.id,
                    pdfFileName('Санкции_' + caseDisplayName(caseData), caseData.iinBin, caseData.id.slice(0, 8)),
                  ).catch((e) => alert(e instanceof Error ? e.message : 'Ошибка выгрузки'))
                }
                className="ml-auto inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-neutral-200 hover:bg-neutral-50 transition-colors"
                title="Скачать санкционное резюме (КТО/ЧТО/ГДЕ/КОГДА/ПОЧЕМУ) в PDF"
              >
                <Download className="w-3.5 h-3.5" />
                Санкционное резюме (PDF)
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-neutral-500">Дата скрининга</p>
                <p className="font-medium text-neutral-900">
                  {new Date(lseg.screenedAt).toLocaleString('ru-RU')}
                </p>
              </div>
              <div>
                <p className="text-neutral-500">Рейтинг <Abbr code="WC1">WC1</Abbr></p>
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
                <h3 className="font-semibold text-neutral-900 flex items-center gap-1 flex-wrap">
                  Санкционные списки (компания)
                  <SourceRef provider="LSEG" />
                </h3>
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
                <h3 className="font-semibold text-neutral-900 flex items-center gap-1 flex-wrap">
                  <Abbr code="PEP">PEP</Abbr>-скрининг (физические лица)
                  <SourceRef provider="LSEG" />
                </h3>
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
          <h3 className="font-semibold text-neutral-900 flex items-center gap-1 flex-wrap">
            <Abbr code="PEP">PEP</Abbr> среди аффилиатов
            <SourceRef provider="LSEG" />
          </h3>
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

      {caseData.deepDiveStatus === 'pending' && allAffiliatesScreened.length === 0 && (
        <div className="rounded-xl bg-white border border-neutral-200">
          <LoadingGif
            message="Скринингуем связанных лиц и аффилиатов через LSEG…"
            size={120}
            className="py-8"
          />
        </div>
      )}
    </div>
  )
}

// ─── Verification log ─────────────────────────────────────────────────────

const ACTION_META: Record<string, { label: string; icon: string; group: 'adata' | 'lseg' | 'ai' | 'system' }> = {
  'company_info':                    { label: 'Базовая информация о компании',        icon: '🏢', group: 'adata' },
  'company_info (cached)':           { label: 'Базовая информация (кэш)',             icon: '🏢', group: 'adata' },
  'director_iin':                    { label: 'ИИН директора',                        icon: '👤', group: 'adata' },
  'director_iin (cached)':           { label: 'ИИН директора (кэш)',                  icon: '👤', group: 'adata' },
  'individual_courts':               { label: 'Персональные судебные дела',           icon: '⚖️', group: 'adata' },
  'individual_courts (cached)':      { label: 'Персональные судебные дела (кэш)',     icon: '⚖️', group: 'adata' },
  'trustworthy_plus':                { label: 'Trustworthy-Plus',                     icon: '📊', group: 'adata' },
  'trustworthy_plus (cached)':       { label: 'Trustworthy-Plus (кэш)',               icon: '📊', group: 'adata' },
  'beneficiary':                     { label: 'Бенефициары (UBO)',                    icon: '🔗', group: 'adata' },
  'beneficiary (cached)':            { label: 'Бенефициары (UBO, кэш)',               icon: '🔗', group: 'adata' },
  'non_resident_affiliations':       { label: 'Нерезиденты',                         icon: '🌍', group: 'adata' },
  'non_resident_affiliations (cached)': { label: 'Нерезиденты (кэш)',                icon: '🌍', group: 'adata' },
  'relation_extended':               { label: 'Связанные лица',                      icon: '🔗', group: 'adata' },
  'relation_extended (cached)':      { label: 'Связанные лица (кэш)',                 icon: '🔗', group: 'adata' },
  'affiliate_tree':                  { label: 'Дерево аффилиатов',                   icon: '🌲', group: 'adata' },
  'affiliate_tree (cached)':         { label: 'Дерево аффилиатов (кэш)',              icon: '🌲', group: 'adata' },
  'director_profile':                { label: 'Профиль директора',                   icon: '👤', group: 'adata' },
  'director_profile (cached)':       { label: 'Профиль директора (кэш)',              icon: '👤', group: 'adata' },
  'affiliate_profile':               { label: 'Данные аффилиата',                    icon: '🏢', group: 'adata' },
  'affiliate_profile (cached)':      { label: 'Данные аффилиата (кэш)',               icon: '🏢', group: 'adata' },
  'lseg:screen':                     { label: 'Скрининг компании и директора',        icon: '🛡️', group: 'lseg' },
  'lseg:extended':                   { label: 'Расширенный скрининг связанных лиц',  icon: '🛡️', group: 'lseg' },
  'lseg:extended_entity':            { label: 'Скрининг связанного лица',            icon: '🛡️', group: 'lseg' },
  'full_report:start':               { label: 'Запуск генерации ИИ-отчёта',          icon: '🤖', group: 'ai' },
  'full_report:section:sanctions':   { label: 'Секция: Санкционный анализ',          icon: '🛡️', group: 'ai' },
  'full_report:section:courts':      { label: 'Секция: Судебные дела',               icon: '⚖️', group: 'ai' },
  'full_report:section:structure':   { label: 'Секция: Структура и аффилиаты',       icon: '🏢', group: 'ai' },
  'full_report:section:summary':     { label: 'Секция: Итоговое резюме',             icon: '📋', group: 'ai' },
  'full_report:saved':               { label: 'ИИ-отчёт сохранён',                  icon: '✅', group: 'ai' },
  'full_report:template':            { label: 'ИИ-отчёт (шаблон, без LLM)',          icon: '📄', group: 'ai' },
  'full_report:openai_error':        { label: 'Ошибка OpenAI',                       icon: '❌', group: 'ai' },
  'conclusion:saved':                { label: 'ИИ-заключение сохранено',             icon: '✅', group: 'ai' },
  'conclusion':                      { label: 'Генерация ИИ-заключения',             icon: '🤖', group: 'ai' },
  'process_case:start':              { label: 'Запуск обработки кейса',              icon: '⚙️', group: 'system' },
}

const MODE_LABELS: Record<string, { label: string; cls: string }> = {
  'llm':                    { label: 'LLM',          cls: 'bg-violet-50 text-violet-700 border-violet-200' },
  'template_fallback':      { label: 'Шаблон',       cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  'deterministic_heuristic':{ label: 'Авто',         cls: 'bg-sky-50 text-sky-700 border-sky-200' },
  'template':               { label: 'Шаблон',       cls: 'bg-amber-50 text-amber-700 border-amber-200' },
}

const GROUP_CONFIG: Record<string, { label: string; headerCls: string; dotCls: string }> = {
  adata:  { label: 'Adata',       headerCls: 'bg-blue-50 border-blue-200 text-blue-700',   dotCls: 'bg-blue-500' },
  lseg:   { label: 'LSEG',        headerCls: 'bg-purple-50 border-purple-200 text-purple-700', dotCls: 'bg-purple-500' },
  ai:     { label: 'ИИ',          headerCls: 'bg-indigo-50 border-indigo-200 text-indigo-700', dotCls: 'bg-indigo-500' },
  system: { label: 'Pipeline',    headerCls: 'bg-neutral-50 border-neutral-200 text-neutral-600', dotCls: 'bg-neutral-400' },
}

// Derive data coverage from actual case fields (works even for old cases without full logs)
function buildDataCoverage(caseData: Case) {
  const e = caseData.enrichment
  const individualCourtCount = caseData.individualCourts
    ? Object.values(caseData.individualCourts).reduce((s, arr) => s + arr.length, 0)
    : 0
  const lsegExtCount = caseData.lsegExtended ? Object.keys(caseData.lsegExtended).length : 0
  const beneficiaryCount = caseData.beneficiary?.length ?? 0
  const treeNodes = (caseData as unknown as Record<string, unknown>).affiliateTree
    ? ((caseData as unknown as Record<string, { nodesCount?: number }>).affiliateTree?.nodesCount ?? '?')
    : null

  const items = [
    {
      label: 'Базовая информация',
      provider: 'Adata',
      available: !!e?.companyInfo,
      detail: e?.companyInfo?.director ? `Директор: ${e.companyInfo.director}` : undefined,
      endpoint: '/company/info',
    },
    {
      label: 'Судебные дела (компания)',
      provider: 'Adata',
      available: !!e?.courts,
      detail: e?.courts ? `${e.courts.activeCases} активных` : undefined,
      endpoint: '/courtcase',
    },
    {
      label: 'Суды (персональные)',
      provider: 'Adata',
      available: individualCourtCount > 0,
      detail: individualCourtCount > 0 ? `${individualCourtCount} дел` : undefined,
      endpoint: '/individual/court-case/details',
    },
    {
      label: 'Бенефициары (UBO)',
      provider: 'Adata',
      available: beneficiaryCount > 0,
      detail: beneficiaryCount > 0 ? `${beneficiaryCount} записей` : undefined,
      endpoint: '/company/beneficiary',
    },
    {
      label: 'Дерево аффилиатов',
      provider: 'Adata',
      available: !!treeNodes,
      detail: treeNodes ? `${treeNodes} узлов` : undefined,
      endpoint: '/company/affiliates',
    },
    {
      label: 'Скрининг компании',
      provider: 'LSEG',
      available: !!caseData.lseg,
      detail: caseData.lseg
        ? ((caseData.lseg.sanctions as { isOnList?: boolean } | undefined)?.isOnList
            ? '⚠ Совпадения найдены'
            : '✓ Чисто')
        : undefined,
      endpoint: 'World-Check One',
    },
    {
      label: 'Расширенный скрининг',
      provider: 'LSEG',
      available: lsegExtCount > 0,
      detail: lsegExtCount > 0 ? `${lsegExtCount} лиц проверено` : undefined,
      endpoint: 'World-Check One (extended)',
    },
    {
      label: 'Полный ИИ-отчёт',
      provider: 'ИИ',
      available:
        !!caseData.hasFullReport ||
        caseData.verificationLog?.some((ev) => ev.action === 'full_report:saved'),
      detail: undefined,
      endpoint: 'OpenAI / Шаблон',
    },
  ]
  return items
}

function VerificationLogTab({ caseData }: { caseData: Case }) {
  const events: VerificationLogEvent[] = caseData.verificationLog ?? []
  const [providerFilter, setProviderFilter] = useState<string>('all')

  const coverage = buildDataCoverage(caseData)

  const sorted = [...events].sort((a, b) => (b.ts || '').localeCompare(a.ts || ''))
  const providers = Array.from(new Set(sorted.map((e) => (e.provider || '').trim()).filter(Boolean))).sort()
  const filtered = providerFilter === 'all' ? sorted : sorted.filter((e) => e.provider === providerFilter)

  const fmt = (iso: string) => {
    try { return new Date(iso).toLocaleString('ru-RU') } catch { return iso }
  }

  const fmtTime = (iso: string) => {
    try { return new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) } catch { return iso }
  }

  return (
    <div className="space-y-5">

      {/* ── Data coverage grid ─────────────────────────────── */}
      <div className="bg-white rounded-xl border border-neutral-200 p-5">
        <div className="flex items-center gap-2 mb-4">
          <Database className="w-4 h-4 text-neutral-500" />
          <h3 className="text-sm font-semibold text-neutral-800">Что собрано по контрагенту</h3>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {coverage.map((item, i) => (
            <div
              key={i}
              className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 ${
                item.available
                  ? 'border-neutral-200 bg-white'
                  : 'border-dashed border-neutral-200 bg-neutral-50 opacity-60'
              }`}
            >
              <span className={`mt-0.5 w-2 h-2 rounded-full shrink-0 ${
                item.available ? 'bg-emerald-500' : 'bg-neutral-300'
              }`} />
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <p className="text-xs font-medium text-neutral-800 leading-tight">{item.label}</p>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-500 border border-neutral-200 shrink-0">
                    <Abbr code={item.provider}>{item.provider}</Abbr>
                  </span>
                </div>
                {item.detail && (
                  <p className="text-[11px] text-neutral-500 mt-0.5">{item.detail}</p>
                )}
                <p className="text-[10px] text-neutral-400 mt-0.5 font-mono truncate">{item.endpoint}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Event timeline ─────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-neutral-200 overflow-hidden">
        {/* Timeline header */}
        <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-neutral-100">
          <div className="flex items-center gap-2">
            <ListChecks className="w-4 h-4 text-neutral-500" />
            <h3 className="text-sm font-semibold text-neutral-800">Хронология событий</h3>
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-neutral-100 text-neutral-500 border border-neutral-200">
              {events.length}
            </span>
          </div>
          {providers.length > 1 && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-neutral-400">Провайдер:</span>
              <select
                value={providerFilter}
                onChange={(e) => setProviderFilter(e.target.value)}
                className="text-xs border border-neutral-200 rounded-lg px-2 py-1.5 bg-white text-neutral-700"
              >
                <option value="all">Все</option>
                {providers.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          )}
        </div>

        {events.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-sm text-neutral-400">Событий пока нет. Запустите проверку или обновите кейс.</p>
          </div>
        ) : (
          <div className="divide-y divide-neutral-50">
            {filtered.map((e, idx) => {
              const meta = ACTION_META[e.action]
              const ok = e.outcome?.status !== 'error'
              const cached = e.outcome?.cached === true
              const outMeta = e.outcome?.meta ?? {}
              const mode = outMeta.mode as string | undefined
              const availableBlocks = Array.isArray(outMeta.availableBlocks)
                ? (outMeta.availableBlocks as string[])
                : null
              const isAiSection = e.action.startsWith('full_report:section:')
              const group = meta?.group ?? 'system'
              const cfg = GROUP_CONFIG[group]
              const subjectLabel = [e.subject?.name, e.subject?.value].filter(Boolean).join(' · ')
              const modeInfo = mode ? (MODE_LABELS[mode] ?? { label: mode, cls: 'bg-neutral-100 text-neutral-600 border-neutral-200' }) : null

              return (
                <div key={`${e.ts}-${idx}`} className="flex gap-0">
                  {/* Left colored indicator */}
                  <div className={`w-1 shrink-0 ${cfg.dotCls}`} />

                  <div className="flex-1 px-4 py-3">
                    {/* Row 1: time + badges */}
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] font-mono text-neutral-400 min-w-[68px]">{fmtTime(e.ts)}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold uppercase tracking-wide ${cfg.headerCls}`}>
                        <Abbr code={e.provider}>{e.provider}</Abbr>
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                        ok ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-red-50 text-red-700 border-red-200'
                      }`}>
                        {ok ? '✓ OK' : '✗ Ошибка'}
                      </span>
                      {cached && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-sky-50 text-sky-600 border border-sky-200">кэш</span>
                      )}
                      {modeInfo && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${modeInfo.cls}`}>{modeInfo.label}</span>
                      )}
                    </div>

                    {/* Row 2: action + subject */}
                    <div className="flex items-baseline gap-1.5 mt-1">
                      <span className="text-base leading-none">{meta?.icon ?? '•'}</span>
                      <p className="text-[13px] font-medium text-neutral-900">
                        {meta?.label ?? e.action}
                        {subjectLabel && (
                          <span className="font-normal text-neutral-500 text-xs ml-1">— {subjectLabel}</span>
                        )}
                      </p>
                    </div>

                    {/* Row 3: endpoint */}
                    {e.request?.endpoint && (
                      <p className="text-[11px] text-neutral-400 mt-0.5 font-mono">
                        → {e.request.endpoint}
                        {e.request.params && Object.keys(e.request.params).length > 0 && (
                          <span className="ml-1 text-neutral-300">
                            ({Object.entries(e.request.params).map(([k, v]) => `${k}=${v}`).join(', ')})
                          </span>
                        )}
                      </p>
                    )}

                    {/* Row 4: counts as chips */}
                    {e.outcome?.counts && Object.keys(e.outcome.counts).length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {Object.entries(e.outcome.counts).slice(0, 8).map(([k, v]) => (
                          <span key={k} className="text-[11px] px-2 py-0.5 rounded-full bg-neutral-100 text-neutral-600 border border-neutral-200">
                            {k}: <strong>{String(v)}</strong>
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Row 5: AI context blocks */}
                    {isAiSection && availableBlocks && availableBlocks.length > 0 && (
                      <div className="mt-2">
                        <p className="text-[10px] uppercase tracking-wide text-neutral-400 mb-1">Данные в контексте ИИ:</p>
                        <div className="flex flex-wrap gap-1">
                          {availableBlocks.map((block, bi) => (
                            <span key={bi} className="text-[11px] px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-100">
                              {block}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Row 6: error */}
                    {e.outcome?.message && (
                      <p className="text-[11px] text-red-600 mt-1.5 bg-red-50 rounded px-2 py-1 border border-red-100">
                        {e.outcome.message}
                      </p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
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
  const [dossierLoading, setDossierLoading] = useState(false)
  const [dossierElapsed, setDossierElapsed] = useState(0)
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
    { id: 'lseg', label: 'LSEG / Санкции', icon: ShieldCheck },
    ...(caseData.osint || caseData.osintStatus
      ? [{ id: 'osint' as Tab, label: 'OSINT', icon: Globe }]
      : []),
    { id: 'log', label: 'Лог проверки', icon: ListChecks },
    { id: 'documents', label: 'Документы', icon: FileText },
    // { id: 'assessment', label: 'Заключение ИИ', icon: AlertTriangle },
    { id: 'chat', label: 'Чат с ИИ', icon: MessageSquare },
  ]

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

  const handleDownloadDossier = async () => {
    setDossierLoading(true)
    setDossierElapsed(0)
    const timer = setInterval(() => setDossierElapsed((s) => s + 1), 1000)
    try {
      await downloadDossier(
        caseData.id,
        pdfFileName(displayName, caseData.iinBin, caseData.id.slice(0, 8)),
      )
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Ошибка выгрузки досье')
    } finally {
      clearInterval(timer)
      setDossierLoading(false)
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
                    <Abbr code="LSEG">LSEG</Abbr> <Abbr code="WC1">WC1</Abbr>
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
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-lg transition-colors border ${
                caseData.fullReportStale
                  ? 'bg-amber-50 hover:bg-amber-100 text-amber-950 border-amber-300'
                  : 'bg-red-50 hover:bg-red-100 text-red-800 border-red-200'
              }`}
            >
              <FileText className="w-4 h-4" />
              Полный отчёт
              {caseData.fullReportStale && (
                <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-amber-200 text-amber-900">
                  граф обновлён
                </span>
              )}
            </Link>
            {/* <Link
              href={`/cases/${caseData.id}/report`}
              className="flex items-center gap-2 px-4 py-2.5 bg-neutral-100 hover:bg-neutral-200 text-neutral-700 text-sm font-medium rounded-lg transition-colors"
            >
              <FileText className="w-4 h-4" />
              Отчёт PDF
            </Link> */}
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
            <button
              type="button"
              onClick={handleDownloadDossier}
              disabled={dossierLoading}
              className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-70 text-white text-sm font-medium rounded-lg transition-colors min-w-[180px] justify-center"
              title="Полное досье (реквизиты, налоги, санкции, суды, аффилиаты) в PDF"
            >
              {dossierLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Готовлю PDF… {dossierElapsed}с
                </>
              ) : (
                <>
                  <FileText className="w-4 h-4" />
                  Полное досье (PDF)
                </>
              )}
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
      {activeTab === 'lseg' && <LsegTab caseData={caseData} focusEntity={focusEntity} />}
      {activeTab === 'osint' && <OsintTab caseData={caseData} />}
      {activeTab === 'log' && <VerificationLogTab caseData={caseData} />}
      {activeTab === 'documents' && <DocumentsTab caseData={caseData} />}
      {activeTab === 'assessment' && <AssessmentTab caseData={caseData} />}
      {activeTab === 'chat' && <ChatTab caseData={caseData} />}
    </div>
  )
}
