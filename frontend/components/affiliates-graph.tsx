'use client'

import { useState, useCallback, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  X,
  Building2,
  User,
  ExternalLink,
  Loader2,
  RefreshCw,
  GitBranch,
} from 'lucide-react'
import { MarkdownContent } from '@/components/markdown-content'
import { fetchNodeReport, lookupCompany, rebuildAffiliateTree } from '@/lib/api'
import { useCases } from '@/lib/cases-context'
import { dataSourceLabel } from '@/lib/data-source-label'
import type {
  AffiliateTree,
  AffiliateTreeNode,
  DataSourceKind,
  NodeReport,
} from '@/lib/types'

interface GraphNode {
  id: string
  name: string
  type: 'company' | 'person' | 'main'
  role?: string
  iinBin?: string
  hasReport?: boolean
}

function truncateLabel(text: string, max = 36): string {
  if (text.length <= max) return text
  return `${text.slice(0, max - 1)}…`
}

function isCompanyBin(iinBin?: string): boolean {
  if (!iinBin) return false
  return iinBin.replace(/\D/g, '').length === 12
}

function toGraphNode(node: AffiliateTreeNode): GraphNode {
  return {
    id: node.id,
    name: node.name,
    type: node.type,
    role: node.role,
    iinBin: node.iinBin,
    hasReport: node.hasReport,
  }
}

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('ru-RU').format(amount) + ' тг'
}

const sourceLabels: Record<NodeReport['source'], string> = {
  main: 'Основное дело',
  cache: 'Кэш дерева (Adata)',
  case: 'Отдельное дело в базе',
}

function levelLabel(level: number): string {
  if (level === 0) return 'Корень'
  if (level === 1) return 'Уровень 1'
  return 'Уровень 2'
}

function TreeNodeCard({
  node,
  onSelect,
}: {
  node: AffiliateTreeNode
  onSelect: (node: GraphNode) => void
}) {
  const isMain = node.type === 'main'
  const isPerson = node.type === 'person'

  return (
    <button
      type="button"
      onClick={() => onSelect(toGraphNode(node))}
      className={`tree-card text-left rounded-lg border px-3 py-2.5 w-[200px] max-w-[220px] shadow-sm transition-shadow hover:shadow-md ${
        isMain
          ? 'bg-blue-600 border-blue-700 text-white'
          : isPerson
            ? 'bg-purple-50 border-purple-200'
            : 'bg-white border-neutral-200'
      }`}
    >
      <div className="flex items-start gap-2">
        <div
          className={`w-8 h-8 rounded-md flex items-center justify-center shrink-0 ${
            isMain ? 'bg-blue-500' : isPerson ? 'bg-purple-100' : 'bg-blue-100'
          }`}
        >
          {isPerson ? (
            <User className={`w-4 h-4 ${isMain ? 'text-white' : 'text-purple-600'}`} />
          ) : (
            <Building2 className={`w-4 h-4 ${isMain ? 'text-white' : 'text-blue-600'}`} />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p
            className={`text-xs font-medium mb-0.5 ${isMain ? 'text-blue-100' : 'text-neutral-400'}`}
          >
            {levelLabel(node.level)}
          </p>
          <p
            className={`text-sm font-semibold leading-snug ${isMain ? 'text-white' : 'text-neutral-900'}`}
          >
            {truncateLabel(node.name, 40)}
          </p>
          {node.role && (
            <p className={`text-xs mt-0.5 line-clamp-2 ${isMain ? 'text-blue-100' : 'text-neutral-500'}`}>
              {node.role}
            </p>
          )}
          {node.iinBin && (
            <p className={`font-mono text-[10px] mt-1 ${isMain ? 'text-blue-200' : 'text-neutral-400'}`}>
              {node.iinBin}
            </p>
          )}
          {node.hasReport && (
            <p className={`text-[10px] mt-1 ${isMain ? 'text-blue-200' : 'text-emerald-600'}`}>
              ✓ данные сохранены
            </p>
          )}
          {node.probeError && (
            <p className="text-[10px] text-amber-600 mt-1">Ошибка проверки</p>
          )}
        </div>
      </div>
    </button>
  )
}

function TreeBranch({
  node,
  onSelect,
}: {
  node: AffiliateTreeNode
  onSelect: (node: GraphNode) => void
}) {
  const children = node.children || []
  const hasChildren = children.length > 0

  return (
    <li>
      <TreeNodeCard node={node} onSelect={onSelect} />
      {hasChildren && (
        <>
          <div className="tree-stem" aria-hidden />
          <ul className="tree-children">
            {children.map((child) => (
              <TreeBranch key={child.id} node={child} onSelect={onSelect} />
            ))}
          </ul>
        </>
      )}
    </li>
  )
}

interface NodePopupProps {
  node: GraphNode
  position: { x: number; y: number }
  onClose: () => void
  onViewFull: () => void
}

function NodePopup({ node, position, onClose, onViewFull }: NodePopupProps) {
  const canLookup =
    (node.type === 'company' || node.type === 'main') && isCompanyBin(node.iinBin)
  const canShowReport = canLookup && (node.type === 'main' || node.hasReport)

  return (
    <div
      className="fixed z-50 bg-white rounded-xl shadow-xl border border-neutral-200 w-80 overflow-hidden"
      style={{
        left: Math.min(position.x, window.innerWidth - 340),
        top: Math.min(position.y, window.innerHeight - 300),
      }}
    >
      <div className="flex items-start justify-between p-4 border-b border-neutral-100">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
              node.type === 'person' ? 'bg-purple-100' : 'bg-blue-100'
            }`}
          >
            {node.type === 'person' ? (
              <User className="w-5 h-5 text-purple-600" />
            ) : (
              <Building2 className="w-5 h-5 text-blue-600" />
            )}
          </div>
          <div className="min-w-0">
            <h4 className="font-semibold text-neutral-900 text-sm">{node.name}</h4>
            {node.role && <p className="text-xs text-neutral-500">{node.role}</p>}
          </div>
        </div>
        <button onClick={onClose} className="p-1 hover:bg-neutral-100 rounded-lg">
          <X className="w-4 h-4 text-neutral-400" />
        </button>
      </div>
      <div className="p-4">
        {node.iinBin && (
          <p className="font-mono text-sm text-neutral-900">{node.iinBin}</p>
        )}
      </div>
      {node.type !== 'main' && (
        <div className="px-4 pb-4">
          <button
            onClick={onViewFull}
            disabled={!canShowReport}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-neutral-300 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg"
          >
            <ExternalLink className="w-4 h-4" />
            Полное заключение
          </button>
          {!canShowReport && canLookup && (
            <p className="text-xs text-neutral-400 mt-2 text-center">
              Нет кэша — дождитесь дерева или нажмите «Перестроить»
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function FullReportModal({
  caseId,
  node,
  onClose,
}: {
  caseId: string
  node: GraphNode
  onClose: () => void
}) {
  const router = useRouter()
  const { upsertCase } = useCases()
  const [loading, setLoading] = useState(true)
  const [opening, setOpening] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<NodeReport | null>(null)

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      if (!node.iinBin || !isCompanyBin(node.iinBin)) {
        setError('Нужен БИН из 12 цифр')
        setLoading(false)
        return
      }
      try {
        const result = await fetchNodeReport(caseId, node.iinBin)
        if (!cancelled) setReport(result)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Данные не найдены')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, [caseId, node.iinBin])

  const riskLevel = report?.riskLevel || report?.assessment?.riskLevel
  const enrichment = report?.enrichment
  const assessment = report?.assessment
  const openCaseId = report?.openCaseId
  const canOpenCase =
    Boolean(node.iinBin && isCompanyBin(node.iinBin)) &&
    (Boolean(openCaseId && openCaseId !== caseId) ||
      (report?.source === 'cache' && Boolean(report?.bin)) ||
      (report?.source === 'case' && Boolean(openCaseId)))

  const handleOpenCase = async () => {
    if (!node.iinBin || !isCompanyBin(node.iinBin)) return
    if (openCaseId && openCaseId !== caseId) {
      router.push(`/cases/${openCaseId}`)
      onClose()
      return
    }
    setOpening(true)
    setError(null)
    try {
      const created = await lookupCompany(
        report?.name || node.name,
        node.iinBin,
        false,
        caseId,
      )
      const targetId = created.id || created.openCaseId || report?.openCaseId
      if (!targetId) {
        throw new Error('API не вернул идентификатор дела')
      }
      if (created.id) {
        upsertCase(created)
      }
      router.push(`/cases/${targetId}`)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось открыть дело')
    } finally {
      setOpening(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between p-6 border-b border-neutral-100 shrink-0">
          <div>
            <h2 className="font-semibold text-lg">{report?.name || node.name}</h2>
            {node.iinBin && <p className="font-mono text-sm text-neutral-400 mt-1">{node.iinBin}</p>}
          </div>
          <button type="button" onClick={onClose}>
            <X className="w-5 h-5 text-neutral-400" />
          </button>
        </div>

        <div className="p-6 overflow-auto flex-1 space-y-4">
          {loading && (
            <div className="flex flex-col items-center py-12 gap-2">
              <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
              <p className="text-sm text-neutral-500">Загрузка из сохранённых данных…</p>
            </div>
          )}
          {error && (
            <p className="text-sm text-red-700 bg-red-50 border border-red-100 rounded-lg p-4">{error}</p>
          )}
          {report && !loading && (
            <>
              <p className="text-xs text-neutral-500">{sourceLabels[report.source]}</p>
              {riskLevel && (
                <p className="text-sm font-medium text-neutral-800">
                  Риск:{' '}
                  {riskLevel === 'low' ? 'низкий' : riskLevel === 'medium' ? 'средний' : 'высокий'}
                </p>
              )}
              {assessment?.summary && (
                <p className="text-sm text-neutral-700">{assessment.summary}</p>
              )}
              {enrichment && (
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="bg-neutral-50 rounded-lg p-3">
                    <p className="text-neutral-500 text-xs">Налоги</p>
                    <p>{formatCurrency(enrichment.taxes.debt)}</p>
                  </div>
                  <div className="bg-neutral-50 rounded-lg p-3">
                    <p className="text-neutral-500 text-xs">Суды (активные)</p>
                    <p>{enrichment.courts.activeCases}</p>
                  </div>
                </div>
              )}
              {assessment?.recommendations && assessment.recommendations.length > 0 && (
                <ul className="text-sm space-y-1 text-neutral-700">
                  {assessment.recommendations.map((r, i) => (
                    <li key={i}>• {r}</li>
                  ))}
                </ul>
              )}
              {report.conclusion && (
                <div className="border-t pt-4">
                  <MarkdownContent className="text-sm">{report.conclusion}</MarkdownContent>
                </div>
              )}
            </>
          )}
        </div>

        {canOpenCase && !loading && (
          <div className="p-4 border-t shrink-0">
            {openCaseId && openCaseId !== caseId ? (
              <Link
                href={`/cases/${openCaseId}`}
                className="block text-center py-2.5 bg-neutral-900 text-white text-sm font-medium rounded-lg hover:bg-neutral-800"
                onClick={onClose}
              >
                Открыть дело
              </Link>
            ) : (
              <button
                type="button"
                onClick={handleOpenCase}
                disabled={opening}
                className="w-full text-center py-2.5 bg-neutral-900 text-white text-sm font-medium rounded-lg hover:bg-neutral-800 disabled:opacity-50"
              >
                {opening ? 'Создание дела…' : 'Открыть дело'}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

interface AffiliatesGraphProps {
  caseId: string
  mainCompany: { name: string; iinBin: string }
  affiliateTree?: AffiliateTree
  source?: DataSourceKind
  onTreeUpdated?: () => void
}

export function AffiliatesGraph({
  caseId,
  mainCompany,
  affiliateTree,
  source = 'stub',
  onTreeUpdated,
}: AffiliatesGraphProps) {
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [popupPosition, setPopupPosition] = useState({ x: 0, y: 0 })
  const [showFullReport, setShowFullReport] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)

  const treeStatus = affiliateTree?.status ?? 'pending'
  const root = affiliateTree?.root
  const isBuilding = treeStatus === 'building'
  const isReady = treeStatus === 'ready' && root

  const handleSelect = useCallback((node: GraphNode) => {
    setSelectedNode(node)
    setPopupPosition({ x: 120, y: 120 })
  }, [])

  const handleRebuild = async () => {
    setRebuilding(true)
    try {
      await rebuildAffiliateTree(caseId)
      onTreeUpdated?.()
    } finally {
      setRebuilding(false)
    }
  }

  return (
    <div className="bg-white rounded-xl border border-neutral-200 p-5">
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <div>
          <h3 className="font-semibold text-neutral-900 flex items-center gap-2">
            <GitBranch className="w-5 h-5 text-neutral-600" />
            Дерево связей
            <span className="text-xs font-normal text-neutral-400">{dataSourceLabel(source)}</span>
          </h3>
          <p className="text-xs text-neutral-500 mt-1">
            Глубина 2: корень → связи Adata → проверка найденных БИН
          </p>
        </div>
        <button
          type="button"
          onClick={handleRebuild}
          disabled={rebuilding || isBuilding}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-neutral-200 rounded-lg hover:bg-neutral-50 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${rebuilding || isBuilding ? 'animate-spin' : ''}`} />
          Перестроить
        </button>
      </div>

      {isBuilding && (
        <div className="flex items-center gap-3 text-sm text-blue-800 bg-blue-50 border border-blue-100 rounded-lg px-4 py-3 mb-4">
          <Loader2 className="w-5 h-5 animate-spin shrink-0" />
          <div>
            <p className="font-medium">Дерево строится в фоне</p>
            <p className="text-xs text-blue-600 mt-0.5">
              Проверено БИН: {affiliateTree?.checkedBins?.length ?? 1}
              {affiliateTree?.nodesCount ? ` · узлов: ${affiliateTree.nodesCount}` : ''}
            </p>
          </div>
        </div>
      )}

      {treeStatus === 'error' && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-100 rounded-lg px-4 py-3 mb-4">
          {affiliateTree?.error || 'Ошибка построения дерева'}
        </div>
      )}

      {treeStatus === 'pending' && !isBuilding && (
        <div className="text-sm text-neutral-600 bg-neutral-50 border border-neutral-100 rounded-lg px-4 py-3 mb-4">
          Дерево будет построено автоматически после завершения проверки дела.
        </div>
      )}

      {root ? (
        <div className="overflow-x-auto border border-neutral-100 rounded-lg bg-neutral-50/80">
          <div className="affiliate-tree min-w-full">
            <ul>
              <TreeBranch node={root} onSelect={handleSelect} />
            </ul>
          </div>
        </div>
      ) : !isBuilding ? (
        <p className="text-sm text-neutral-500 py-8 text-center">
          {source === 'adata'
            ? 'Связи не найдены или дерево ещё не готово.'
            : 'Нет данных Adata для дерева.'}
        </p>
      ) : null}

      {isReady && affiliateTree && (
        <p className="text-xs text-neutral-400 mt-3">
          Узлов: {affiliateTree.nodesCount}
          {affiliateTree.builtAt &&
            ` · обновлено ${new Date(affiliateTree.builtAt).toLocaleString('ru-RU')}`}
        </p>
      )}

      <p className="text-xs text-neutral-400 mt-2">Нажмите на узел для карточки и полного заключения</p>

      {selectedNode && !showFullReport && (
        <NodePopup
          node={selectedNode}
          position={popupPosition}
          onClose={() => setSelectedNode(null)}
          onViewFull={() => setShowFullReport(true)}
        />
      )}

      {showFullReport && selectedNode && (
        <FullReportModal
          caseId={caseId}
          node={selectedNode}
          onClose={() => {
            setShowFullReport(false)
            setSelectedNode(null)
          }}
        />
      )}
    </div>
  )
}
