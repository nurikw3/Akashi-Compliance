'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  ChevronDown,
  ChevronRight,
  GitBranch,
  LayoutGrid,
  List,
  Loader2,
  Network,
} from 'lucide-react'
import { useCases } from '@/lib/cases-context'
import { buildCaseGroups } from '@/lib/case-groups'
import type { Case } from '@/lib/types'

type ViewMode = 'list' | 'grid'

const VIEW_STORAGE_KEY = 'akashi-cases-view'

function RiskBadge({ level, status }: { level: Case['riskLevel']; status: Case['status'] }) {
  if (status === 'pending' || status === 'enriching') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-neutral-100 text-neutral-600">
        <Loader2 className="w-3 h-3 animate-spin" />
        {status === 'pending' ? 'Ожидание' : 'Проверка...'}
      </span>
    )
  }

  if (status === 'error') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700">
        Ошибка
      </span>
    )
  }

  const config = {
    low: { bg: 'bg-emerald-100', text: 'text-emerald-700', dot: 'bg-emerald-500', label: 'Низкий риск' },
    medium: { bg: 'bg-amber-100', text: 'text-amber-700', dot: 'bg-amber-500', label: 'Средний риск' },
    high: { bg: 'bg-red-100', text: 'text-red-700', dot: 'bg-red-500', label: 'Высокий риск' },
  }

  const c = level ? config[level] : config.low

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${c.bg} ${c.text}`}>
      <span className={`w-2 h-2 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  )
}

function CaseMeta({ caseItem }: { caseItem: Case }) {
  return (
    <p className="text-sm text-neutral-500">
      <span className="font-mono">{caseItem.iinBin}</span>
      <span className="mx-2">•</span>
      <span>{caseItem.createdAt.toLocaleDateString('ru-RU')}</span>
    </p>
  )
}

function ViewToggle({
  viewMode,
  onChange,
}: {
  viewMode: ViewMode
  onChange: (mode: ViewMode) => void
}) {
  return (
    <div className="inline-flex rounded-lg border border-neutral-200 bg-white p-0.5">
      <button
        type="button"
        onClick={() => onChange('list')}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
          viewMode === 'list'
            ? 'bg-neutral-900 text-white'
            : 'text-neutral-600 hover:bg-neutral-50'
        }`}
        aria-pressed={viewMode === 'list'}
      >
        <List className="w-4 h-4" />
        Список
      </button>
      <button
        type="button"
        onClick={() => onChange('grid')}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
          viewMode === 'grid'
            ? 'bg-neutral-900 text-white'
            : 'text-neutral-600 hover:bg-neutral-50'
        }`}
        aria-pressed={viewMode === 'grid'}
      >
        <LayoutGrid className="w-4 h-4" />
        Сетка
      </button>
    </div>
  )
}

function CaseRowLink({
  caseItem,
  nested = false,
}: {
  caseItem: Case
  nested?: boolean
}) {
  return (
    <Link
      href={`/cases/${caseItem.id}`}
      className={`flex items-center gap-4 hover:bg-neutral-50 transition-colors ${
        nested ? 'pl-10 pr-4 py-3 bg-neutral-50/80' : 'p-4'
      }`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3 mb-1 flex-wrap">
          {nested && <GitBranch className="w-3.5 h-3.5 text-neutral-400 shrink-0" />}
          <h3
            className={`truncate ${nested ? 'text-sm font-medium text-neutral-700' : 'font-medium text-neutral-900'}`}
          >
            {caseItem.name}
          </h3>
          <RiskBadge level={caseItem.riskLevel} status={caseItem.status} />
        </div>
        <CaseMeta caseItem={caseItem} />
      </div>
      <ChevronRight className="w-5 h-5 text-neutral-400 flex-shrink-0" />
    </Link>
  )
}

function CaseCardLink({ caseItem, compact = false }: { caseItem: Case; compact?: boolean }) {
  return (
    <Link
      href={`/cases/${caseItem.id}`}
      className={`block rounded-lg border border-neutral-100 hover:border-neutral-200 hover:bg-neutral-50 transition-colors ${
        compact ? 'p-3' : 'p-4'
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3
          className={`font-medium text-neutral-900 line-clamp-2 ${compact ? 'text-sm' : ''}`}
          title={caseItem.name}
        >
          {caseItem.name}
        </h3>
        <ChevronRight className="w-4 h-4 text-neutral-400 shrink-0 mt-0.5" />
      </div>
      <div className="mb-2">
        <RiskBadge level={caseItem.riskLevel} status={caseItem.status} />
      </div>
      <CaseMeta caseItem={caseItem} />
    </Link>
  )
}

function CaseGroupBlock({
  group,
  viewMode,
  expanded,
  onToggle,
}: {
  group: ReturnType<typeof buildCaseGroups>[number]
  viewMode: ViewMode
  expanded: boolean
  onToggle: () => void
}) {
  const hasRelated = group.related.length > 0

  if (viewMode === 'grid') {
    return (
      <div className="bg-white rounded-xl border border-neutral-200 overflow-hidden flex flex-col">
        <div className="p-1 flex-1">
          <CaseCardLink caseItem={group.primary} />
        </div>
        {hasRelated && (
          <div className="border-t border-neutral-100 px-3 pb-3">
            <button
              type="button"
              onClick={onToggle}
              className="w-full flex items-center justify-between gap-2 py-2.5 text-sm text-neutral-600 hover:text-neutral-900"
            >
              <span className="inline-flex items-center gap-2">
                <Network className="w-4 h-4" />
                {expanded
                  ? 'Скрыть связанные'
                  : `Связанные по графу (${group.related.length})`}
              </span>
              <ChevronDown
                className={`w-4 h-4 transition-transform ${expanded ? 'rotate-180' : ''}`}
              />
            </button>
            {expanded && (
              <div className="space-y-2">
                {group.related.map((item) => (
                  <CaseCardLink key={item.id} caseItem={item} compact />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="divide-y divide-neutral-100">
      <div className="flex items-stretch">
        {hasRelated ? (
          <button
            type="button"
            onClick={onToggle}
            className="flex items-center justify-center w-10 shrink-0 hover:bg-neutral-50 border-r border-neutral-100"
            aria-expanded={expanded}
            aria-label={expanded ? 'Свернуть связанные' : 'Показать связанные'}
          >
            <ChevronDown
              className={`w-4 h-4 text-neutral-500 transition-transform ${
                expanded ? 'rotate-180' : '-rotate-90'
              }`}
            />
          </button>
        ) : (
          <div className="w-10 shrink-0 border-r border-neutral-100" />
        )}
        <div className="flex-1 min-w-0">
          <CaseRowLink caseItem={group.primary} />
        </div>
      </div>
      {hasRelated && expanded && (
        <div className="border-t border-neutral-100 bg-neutral-50/50">
          <p className="px-4 pt-2 pb-1 text-xs font-medium text-neutral-400 uppercase tracking-wide">
            Связанные по графу
          </p>
          {group.related.map((item) => (
            <CaseRowLink key={item.id} caseItem={item} nested />
          ))}
        </div>
      )}
      {hasRelated && !expanded && (
        <button
          type="button"
          onClick={onToggle}
          className="w-full py-2 text-xs text-neutral-500 hover:text-neutral-700 hover:bg-neutral-50 border-t border-neutral-100"
        >
          +{group.related.length} связанных по графу
        </button>
      )}
    </div>
  )
}

export function CasesList() {
  const { cases } = useCases()
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    const stored = localStorage.getItem(VIEW_STORAGE_KEY)
    if (stored === 'list' || stored === 'grid') setViewMode(stored)
  }, [])

  const setView = (mode: ViewMode) => {
    setViewMode(mode)
    localStorage.setItem(VIEW_STORAGE_KEY, mode)
  }

  const groups = useMemo(() => buildCaseGroups(cases), [cases])

  const toggleGroup = (groupId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(groupId)) next.delete(groupId)
      else next.add(groupId)
      return next
    })
  }

  if (cases.length === 0) {
    return (
      <div className="text-center py-16">
        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-neutral-100 flex items-center justify-center">
          <svg className="w-8 h-8 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        </div>
        <h3 className="text-lg font-medium text-neutral-900 mb-2">Нет дел</h3>
        <p className="text-neutral-500 mb-6">Загрузите Excel файл, чтобы создать первые дела</p>
        <Link
          href="/"
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          Загрузить файл
        </Link>
      </div>
    )
  }

  const stats = {
    total: cases.length,
    groups: groups.length,
    linked: cases.length - groups.length,
    low: cases.filter((c) => c.riskLevel === 'low').length,
    medium: cases.filter((c) => c.riskLevel === 'medium').length,
    high: cases.filter((c) => c.riskLevel === 'high').length,
    processing: cases.filter((c) => c.status === 'pending' || c.status === 'enriching').length,
  }

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
        <div className="bg-white rounded-xl border border-neutral-200 p-4">
          <p className="text-2xl font-semibold text-neutral-900">{stats.groups}</p>
          <p className="text-sm text-neutral-500">Групп на экране</p>
        </div>
        <div className="bg-white rounded-xl border border-neutral-200 p-4">
          <p className="text-2xl font-semibold text-emerald-600">{stats.low}</p>
          <p className="text-sm text-neutral-500">Низкий риск</p>
        </div>
        <div className="bg-white rounded-xl border border-neutral-200 p-4">
          <p className="text-2xl font-semibold text-amber-600">{stats.medium}</p>
          <p className="text-sm text-neutral-500">Средний риск</p>
        </div>
        <div className="bg-white rounded-xl border border-neutral-200 p-4">
          <p className="text-2xl font-semibold text-red-600">{stats.high}</p>
          <p className="text-sm text-neutral-500">Высокий риск</p>
        </div>
        <div className="bg-white rounded-xl border border-neutral-200 p-4 col-span-2 sm:col-span-1">
          <p className="text-2xl font-semibold text-neutral-600">{stats.processing}</p>
          <p className="text-sm text-neutral-500">В обработке</p>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <p className="text-sm text-neutral-500">
          {stats.total} дел
          {stats.linked > 0 && (
            <span>
              {' '}
              · {stats.linked} скрыто в группах по графу
            </span>
          )}
        </p>
        <ViewToggle viewMode={viewMode} onChange={setView} />
      </div>

      {viewMode === 'grid' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {groups.map((group) => (
            <CaseGroupBlock
              key={group.id}
              group={group}
              viewMode="grid"
              expanded={expandedIds.has(group.id)}
              onToggle={() => toggleGroup(group.id)}
            />
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-neutral-200 overflow-hidden divide-y divide-neutral-100">
          {groups.map((group) => (
            <CaseGroupBlock
              key={group.id}
              group={group}
              viewMode="list"
              expanded={expandedIds.has(group.id)}
              onToggle={() => toggleGroup(group.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
