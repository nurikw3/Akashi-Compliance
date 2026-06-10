'use client'

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  Panel,
  useReactFlow,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from 'dagre'
import {
  X,
  Building2,
  User,
  ExternalLink,
  Loader2,
  RefreshCw,
  GitBranch,
  Maximize2,
} from 'lucide-react'
import { LoadingGif } from '@/components/loading-gif'
import { MarkdownContent } from '@/components/markdown-content'
import { Abbr } from '@/components/ui/abbr'
import { fetchNodeReport, lookupCompany, rebuildAffiliateTree } from '@/lib/api'
import { useCases } from '@/lib/cases-context'
import type {
  AffiliateTree,
  AffiliateTreeNode,
  DataSourceKind,
  LsegData,
  LsegExtendedEntity,
  NodeReport,
} from '@/lib/types'

interface GraphNode {
  id: string
  name: string
  type: 'company' | 'person' | 'main'
  role?: string
  iinBin?: string
  hasReport?: boolean
  probeError?: string
  level?: number
  isPep?: boolean
  isBeneficiary?: boolean
  isSanctioned?: boolean
  courtCount?: number
  hiddenChildCount?: number
  directHiddenCount?: number
  isCollapsed?: boolean
  isExpanded?: boolean
  hasCollapsibleChildren?: boolean
  onToggleExpand?: () => void
}

type GraphContextValue = {
  onToggleExpand: (nodeId: string) => void
  onSelect: (node: GraphNode, event: React.MouseEvent) => void
}

const GraphContext = React.createContext<GraphContextValue | null>(null)

type AffiliateNodeData = GraphNode & Record<string, unknown>

const NODE_WIDTH = 240
const NODE_HEIGHT = 120

function truncateLabel(text: string, max = 25): string {
  if (text.length <= max) return text
  return `${text.slice(0, max - 1)}…`
}

function formatRoleLabel(node: GraphNode): string {
  const parts: string[] = []
  if (node.role) parts.push(truncateLabel(node.role, 18))
  if (node.isBeneficiary) parts.push('Бенефициар')
  if (node.isPep) parts.push('PEP')
  if ((node.courtCount ?? 0) > 0) {
    parts.push(`${node.courtCount} судебных дел`)
  }
  return parts.join(' · ')
}

function normalizeBin(value?: string): string {
  if (!value) return ''
  return value.replace(/\D/g, '')
}

function namesMatch(a: string, b: string): boolean {
  const na = a.trim().toLowerCase()
  const nb = b.trim().toLowerCase()
  if (!na || !nb) return false
  return na === nb || na.includes(nb) || nb.includes(na)
}

function countDescendants(node: AffiliateTreeNode): number {
  return (node.children || []).reduce((sum, c) => sum + 1 + countDescendants(c), 0)
}

function buildNodeMeta(
  node: AffiliateTreeNode,
  ctx: {
    lseg?: LsegData | null
    lsegExtended?: Record<string, LsegExtendedEntity> | null
    affiliateProfiles?: Record<string, { courts?: { activeCases?: number; completedCases?: number; cases?: unknown[] } }>
    beneficiary?: Record<string, unknown>[]
  },
): Pick<GraphNode, 'isPep' | 'isBeneficiary' | 'isSanctioned' | 'courtCount'> {
  const bin = normalizeBin(node.iinBin)
  const name = node.name

  let isPep = false
  if (ctx.lseg?.pep?.individuals) {
    isPep = ctx.lseg.pep.individuals.some((ind) => {
      const submitted = ind.submittedName || ind.primaryName || ''
      return namesMatch(name, submitted) || (bin && submitted.includes(bin))
    })
  }
  if (!isPep && ctx.lsegExtended) {
    for (const entity of Object.values(ctx.lsegExtended)) {
      if (namesMatch(name, entity.name) && entity.hits.some((h) => h.isPep)) {
        isPep = true
        break
      }
    }
  }

  let isBeneficiary = (node.role || '').toLowerCase().includes('бенефициар')
  if (!isBeneficiary && ctx.beneficiary) {
    isBeneficiary = ctx.beneficiary.some((b) => {
      const bName = String(b.name || b.short_name || '')
      const bBin = normalizeBin(String(b.biin || b.iin || b.bin || ''))
      return (bin && bBin === bin) || namesMatch(name, bName)
    })
  }

  let isSanctioned = false
  if (ctx.lsegExtended) {
    for (const entity of Object.values(ctx.lsegExtended)) {
      if (namesMatch(name, entity.name) && entity.isOnSanctionList) {
        isSanctioned = true
        break
      }
    }
  }

  let courtCount = 0
  if (bin && ctx.affiliateProfiles?.[bin]?.courts) {
    const courts = ctx.affiliateProfiles[bin].courts!
    courtCount = (courts.activeCases || 0) + (courts.completedCases || 0)
    if (courtCount === 0 && courts.cases?.length) {
      courtCount = courts.cases.length
    }
  }

  return { isPep, isBeneficiary, isSanctioned, courtCount }
}

function applyCollapse(
  node: AffiliateTreeNode,
  expandedIds: Set<string>,
  ctx: Parameters<typeof buildNodeMeta>[1],
  level = 0,
): AffiliateTreeNode & { _meta?: GraphNode } {
  const children = node.children || []
  const isExpanded = expandedIds.has(node.id)
  const meta = buildNodeMeta(node, ctx)
  const hasCollapsibleChildren = level >= 1 && children.length > 0

  if (hasCollapsibleChildren && !isExpanded) {
    return {
      ...node,
      children: [],
      _meta: {
        ...toGraphNode(node),
        ...meta,
        hiddenChildCount: countDescendants(node),
        directHiddenCount: children.length,
        isCollapsed: true,
        isExpanded: false,
        hasCollapsibleChildren: true,
      },
    }
  }

  return {
    ...node,
    children: children.map((c) => applyCollapse(c, expandedIds, ctx, level + 1)),
    _meta: {
      ...toGraphNode(node),
      ...meta,
      isCollapsed: false,
      isExpanded: hasCollapsibleChildren && isExpanded,
      hasCollapsibleChildren,
      directHiddenCount: hasCollapsibleChildren ? children.length : undefined,
      hiddenChildCount: hasCollapsibleChildren ? countDescendants(node) : undefined,
    },
  }
}

function countHiddenNodes(node: AffiliateTreeNode, expandedIds: Set<string>, level = 0): number {
  const children = node.children || []
  if (level >= 1 && children.length > 0 && !expandedIds.has(node.id)) {
    return countDescendants(node)
  }
  return children.reduce((sum, c) => sum + countHiddenNodes(c, expandedIds, level + 1), 0)
}

function isCompanyBin(iinBin?: string): boolean {
  if (!iinBin) return false
  return iinBin.replace(/\D/g, '').length === 12
}

function isForeignEntity(node: Pick<GraphNode, 'type' | 'iinBin'>): boolean {
  return node.type === 'company' && !isCompanyBin(node.iinBin)
}

function toGraphNode(node: AffiliateTreeNode): GraphNode {
  return {
    id: node.id,
    name: node.name,
    type: node.type,
    role: node.role,
    iinBin: node.iinBin,
    hasReport: node.hasReport,
    probeError: node.probeError,
    level: node.level,
  }
}

function getLayoutedElements(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 48, ranksep: 72, marginx: 24, marginy: 24 })

  nodes.forEach((node) => {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  })
  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target)
  })

  dagre.layout(g)

  const layoutedNodes = nodes.map((node) => {
    const pos = g.node(node.id)
    return {
      ...node,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    }
  })

  return { nodes: layoutedNodes, edges }
}

function treeToFlow(root: AffiliateTreeNode & { _meta?: GraphNode }): { nodes: Node<AffiliateNodeData>[]; edges: Edge[] } {
  const nodes: Node<AffiliateNodeData>[] = []
  const edges: Edge[] = []

  const walk = (node: AffiliateTreeNode & { _meta?: GraphNode }, parentId?: string) => {
    const data: GraphNode = node._meta ?? toGraphNode(node)
    nodes.push({
      id: node.id,
      type: 'affiliate',
      position: { x: 0, y: 0 },
      data: data as AffiliateNodeData,
      draggable: false,
    })
    if (parentId) {
      const dashed = (data.level ?? 0) >= 2
      edges.push({
        id: `${parentId}->${node.id}`,
        source: parentId,
        target: node.id,
        type: 'smoothstep',
        style: {
          stroke: '#94a3b8',
          strokeWidth: 1.5,
          strokeDasharray: dashed ? '5 4' : undefined,
        },
      })
    }
    for (const child of node.children || []) {
      walk(child as AffiliateTreeNode & { _meta?: GraphNode }, node.id)
    }
  }

  walk(root)
  return { nodes, edges }
}

function AffiliateFlowNode({ data }: NodeProps<Node<AffiliateNodeData>>) {
  const ctx = React.useContext(GraphContext)
  const isMain = data.type === 'main'
  const isPerson = data.type === 'person'
  const isForeign = isForeignEntity(data)
  const roleLabel = formatRoleLabel(data)

  let borderClass = 'border-neutral-300 bg-neutral-100 text-neutral-900'
  if (isMain) {
    borderClass = 'border-blue-500 bg-blue-700 text-white shadow-md'
  } else if (data.isBeneficiary || data.isSanctioned) {
    borderClass = 'border-rose-300 bg-rose-100 text-rose-950'
  } else if (data.isPep || isPerson) {
    borderClass = 'border-amber-300 bg-amber-50 text-amber-950'
  } else if (isForeign) {
    borderClass = 'border-orange-400 bg-orange-50 text-orange-950'
  } else if (data.hasReport) {
    borderClass = 'border-blue-400 bg-white text-neutral-900'
  }

  const openDetails = (event: React.MouseEvent) => {
    event.preventDefault()
    event.stopPropagation()
    ctx?.onSelect(data, event)
  }

  const canOpenDetails =
    isMain ||
    isForeign ||
    isCompanyBin(data.iinBin) ||
    data.type === 'person' ||
    Boolean(data.hasReport)

  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-slate-500 !w-2 !h-2 !border-0" />
      <div
        className={`nodrag nopan rounded-lg border shadow-sm transition-shadow hover:shadow-md w-[240px] ${borderClass}`}
      >
        <button
          type="button"
          onClick={openDetails}
          className={`nodrag nopan w-full text-left px-3 py-2.5 rounded-t-lg ${
            canOpenDetails ? 'cursor-pointer hover:brightness-[0.98]' : 'cursor-default'
          }`}
        >
          <div className="min-w-0">
            <div className="flex items-start gap-1.5">
              <p
                className={`text-sm font-semibold leading-snug flex-1 ${isMain ? 'text-white' : ''}`}
                title={data.name}
              >
                {truncateLabel(data.name, 22)}
              </p>
            </div>
            {roleLabel && (
              <p
                className={`text-[11px] mt-1 line-clamp-2 leading-snug ${isMain ? 'text-blue-100' : 'opacity-80'}`}
                title={roleLabel}
              >
                {roleLabel}
              </p>
            )}
            {isForeign && (
              <p className="text-[10px] mt-0.5 text-orange-700 font-medium">⚠ Нерезидент</p>
            )}
            {data.probeError && (
              <p className="text-[10px] text-amber-700 mt-0.5">Ошибка проверки</p>
            )}
          </div>
        </button>

        {(canOpenDetails || data.hasCollapsibleChildren) && (
          <div className="px-2 pb-2 space-y-1.5 border-t border-black/5">
            {canOpenDetails && (
              <button
                type="button"
                onClick={openDetails}
                className="nodrag nopan block w-full text-[10px] px-2 py-1.5 rounded-md font-semibold bg-neutral-900 text-white hover:bg-neutral-800"
              >
                Подробнее
              </button>
            )}
            {data.hasCollapsibleChildren && (
              <>
                {!data.isExpanded && (data.hiddenChildCount ?? 0) > (data.directHiddenCount ?? 0) && (
                  <span className="inline-block text-[10px] px-2 py-0.5 rounded-full bg-neutral-200 text-neutral-600 border border-neutral-300">
                    +{data.hiddenChildCount} узлов…
                  </span>
                )}
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    ctx?.onToggleExpand(data.id)
                  }}
                  className={`nodrag nopan block w-full text-[10px] px-2 py-1 rounded-md font-medium ${
                    data.isExpanded
                      ? 'bg-neutral-100 text-neutral-700 border border-neutral-300 hover:bg-neutral-200'
                      : 'bg-white/90 text-blue-700 border border-blue-300 hover:bg-blue-50'
                  }`}
                >
                  {data.isExpanded
                    ? `− свернуть ${data.directHiddenCount} дочерних`
                    : `+ раскрыть ${data.directHiddenCount} дочерних`}
                </button>
              </>
            )}
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-slate-500 !w-2 !h-2 !border-0" />
    </>
  )
}

const nodeTypes = {
  affiliate: AffiliateFlowNode,
}

function FitViewButton() {
  const { fitView } = useReactFlow()
  return (
    <button
      type="button"
      onClick={() => fitView({ padding: 0.15, duration: 300 })}
      className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs bg-white border border-neutral-200 rounded-md shadow-sm hover:bg-neutral-50"
      title="Показать всё дерево"
    >
      <Maximize2 className="w-3.5 h-3.5" />
      Вписать
    </button>
  )
}

function FlowCanvas({
  root,
  fullRoot,
  expandedIds,
  onToggleExpand,
  onSelect,
  onHover,
  onHoverEnd,
  hiddenTotal,
}: {
  root: AffiliateTreeNode & { _meta?: GraphNode }
  fullRoot: AffiliateTreeNode
  expandedIds: Set<string>
  onToggleExpand: (nodeId: string) => void
  onSelect: (node: GraphNode, event: React.MouseEvent) => void
  onHover: (node: GraphNode, event: React.MouseEvent) => void
  onHoverEnd: () => void
  hiddenTotal: number
}) {
  const graphCtx = useMemo(
    () => ({ onToggleExpand, onSelect }),
    [onToggleExpand, onSelect],
  )

  const { nodes: rawNodes, edges: rawEdges } = useMemo(() => treeToFlow(root), [root])
  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(
    () => getLayoutedElements(rawNodes, rawEdges),
    [rawNodes, rawEdges],
  )

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutedNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutedEdges)
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null)

  useEffect(() => {
    setNodes(layoutedNodes)
    setEdges(layoutedEdges)
  }, [layoutedNodes, layoutedEdges, setNodes, setEdges])

  useEffect(() => {
    if (!rfInstance || layoutedNodes.length === 0) return
    const timer = window.setTimeout(() => {
      rfInstance.fitView({ padding: 0.15, duration: 250 })
    }, 80)
    return () => window.clearTimeout(timer)
  }, [rfInstance, layoutedNodes, root.id, expandedIds.size])

  const onNodeMouseEnter = useCallback(
    (event: React.MouseEvent, node: Node) => {
      onHover(node.data as unknown as GraphNode, event)
    },
    [onHover],
  )

  return (
    <GraphContext.Provider value={graphCtx}>
      <div className="h-[min(70vh,640px)] w-full rounded-lg border border-neutral-200 bg-neutral-50 overflow-hidden">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          onInit={setRfInstance}
          onNodeMouseEnter={onNodeMouseEnter}
          onNodeMouseLeave={onHoverEnd}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.08}
          maxZoom={1.8}
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnScroll
          zoomOnScroll
          zoomOnPinch
        >
          <Background gap={20} size={1} color="#e5e7eb" />
          <Controls
            showInteractive={false}
            position="bottom-right"
            className="!bg-white !border-neutral-200 !shadow-sm [&_button]:!bg-white [&_button]:!border-neutral-200 [&_button]:!text-neutral-700 [&_button:hover]:!bg-neutral-50"
          />
          <MiniMap
            nodeStrokeWidth={2}
            pannable
            zoomable
            className="!bg-white !border !border-neutral-200 !rounded-lg !shadow-sm"
            maskColor="rgba(243, 244, 246, 0.75)"
          />
          <Panel position="top-right">
            <FitViewButton />
          </Panel>
          {hiddenTotal > 0 && (
            <Panel position="bottom-left">
              <span className="text-[11px] px-2.5 py-1 rounded-full bg-white text-neutral-600 border border-neutral-200 shadow-sm">
                +{hiddenTotal} узлов…
              </span>
            </Panel>
          )}
        </ReactFlow>
      </div>
    </GraphContext.Provider>
  )
}

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('ru-RU').format(amount) + ' тг'
}

const sourceLabels: Record<NodeReport['source'], string> = {
  main: 'Основное дело',
  cache: 'Кэш дерева (Adata)',
  case: 'Отдельное дело в базе',
}

interface NodeTooltipProps {
  node: GraphNode
  position: { x: number; y: number }
}

function NodeTooltip({ node, position }: NodeTooltipProps) {
  return (
    <div
      className="fixed z-40 pointer-events-none bg-neutral-900 text-white text-xs rounded-lg px-3 py-2 shadow-lg max-w-xs"
      style={{
        left: Math.min(position.x + 12, window.innerWidth - 260),
        top: Math.min(position.y + 12, window.innerHeight - 120),
      }}
    >
      <p className="font-semibold">{node.name}</p>
      {node.role && <p className="text-neutral-300 mt-0.5">{node.role}</p>}
      {node.iinBin && <p className="font-mono text-neutral-400 mt-1">{node.iinBin}</p>}
      {node.hasReport && <p className="text-blue-300 mt-1">✓ данные сохранены</p>}
      {isForeignEntity(node) && (
        <p className="text-red-300 mt-1">⚠ Нерезидент · проверка через LSEG</p>
      )}
      {isCompanyBin(node.iinBin) && (
        <p className="text-neutral-400 mt-1">Кнопка «Подробнее» на узле — карточка и дело</p>
      )}
    </div>
  )
}

interface NodePopupProps {
  node: GraphNode
  position: { x: number; y: number }
  onClose: () => void
  onViewFull: () => void
  onCheckLseg: () => void
}

function NodePopup({ node, position, onClose, onViewFull, onCheckLseg }: NodePopupProps) {
  const hasBin = isCompanyBin(node.iinBin)
  const canLookup =
    (node.type === 'company' || node.type === 'main' || hasBin) && hasBin
  const isForeign = node.type === 'company' && !hasBin
  const buttonEnabled = isForeign || canLookup
  const handlePrimaryAction = isForeign ? onCheckLseg : onViewFull
  const primaryLabel = isForeign
    ? <>Проверить в <Abbr code="LSEG">LSEG</Abbr></>
    : node.hasReport
      ? 'Полное заключение'
      : 'Загрузить заключение'

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
            {isForeign && (
              <p className="text-[11px] text-red-600 font-medium mt-0.5">⚠ Нерезидент</p>
            )}
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
      {(node.type === 'main' ? canLookup : node.type !== 'main') && (
        <div className="px-4 pb-4">
          <button
            onClick={handlePrimaryAction}
            disabled={!buttonEnabled}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-neutral-300 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg"
          >
            <ExternalLink className="w-4 h-4" />
            {node.type === 'main' ? 'Полное заключение' : primaryLabel}
          </button>
          {canLookup && !node.hasReport && !isForeign && (
            <p className="text-xs text-neutral-400 mt-2 text-center">
              Данные по узлу ещё не в кэше — откроется окно, можно запустить проверку Adata
            </p>
          )}
          {isForeign && (
            <p className="text-xs text-neutral-400 mt-2 text-center">
              Откроется вкладка <Abbr code="LSEG">LSEG</Abbr> родительского дела
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
        !report,
        caseId,
      )
      const targetId = created.id || report?.openCaseId
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
            <LoadingGif message="Загрузка из сохранённых данных…" size={120} className="py-8" />
          )}
          {error && (
            <div className="space-y-3">
              <p className="text-sm text-red-700 bg-red-50 border border-red-100 rounded-lg p-4">
                {error}
              </p>
              {node.iinBin && isCompanyBin(node.iinBin) && (
                <button
                  type="button"
                  onClick={handleOpenCase}
                  disabled={opening}
                  className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg"
                >
                  {opening ? 'Запуск проверки…' : 'Запустить проверку Adata'}
                </button>
              )}
            </div>
          )}
          {report && !loading && (
            <>
              <p className="text-xs text-neutral-500">{sourceLabels[report.source]}</p>
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
              {assessment?.flags && assessment.flags.length > 0 && (
                <ul className="text-sm space-y-1 text-neutral-700">
                  {assessment.flags.map((f, i) => (
                    <li key={i}>• {f.message}</li>
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
  onNodeClick?: (node: GraphNode) => void
  lseg?: LsegData | null
  lsegExtended?: Record<string, LsegExtendedEntity> | null
  affiliateProfiles?: Record<string, { courts?: { activeCases?: number; completedCases?: number; cases?: unknown[] } }>
  beneficiary?: Record<string, unknown>[]
}

export function AffiliatesGraph({
  caseId,
  mainCompany,
  affiliateTree,
  source = 'none',
  onTreeUpdated,
  onNodeClick,
  lseg,
  lsegExtended,
  affiliateProfiles,
  beneficiary,
}: AffiliatesGraphProps) {
  const router = useRouter()
  const { upsertCase } = useCases()
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [popupPosition, setPopupPosition] = useState({ x: 0, y: 0 })
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 })
  const [navigatingBin, setNavigatingBin] = useState<string | null>(null)
  const [showFullReport, setShowFullReport] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set())

  const treeStatus = affiliateTree?.status ?? 'pending'
  const root = affiliateTree?.root
  const isBuilding = treeStatus === 'building'
  const isReady = treeStatus === 'ready' && root

  const graphCtx = useMemo(
    () => ({ lseg, lsegExtended, affiliateProfiles, beneficiary }),
    [lseg, lsegExtended, affiliateProfiles, beneficiary],
  )

  const visibleRoot = useMemo(() => {
    if (!root) return null
    return applyCollapse(root, expandedIds, graphCtx)
  }, [root, expandedIds, graphCtx])

  const hiddenTotal = useMemo(() => {
    if (!root) return 0
    return countHiddenNodes(root, expandedIds)
  }, [root, expandedIds])

  const handleToggleExpand = useCallback((nodeId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(nodeId)) next.delete(nodeId)
      else next.add(nodeId)
      return next
    })
  }, [])

  const handleSelect = useCallback((node: GraphNode, event: React.MouseEvent) => {
    setSelectedNode(node)
    setPopupPosition({ x: event.clientX, y: event.clientY })
  }, [])

  const handleHover = useCallback((node: GraphNode, event: React.MouseEvent) => {
    setHoveredNode(node)
    setTooltipPosition({ x: event.clientX, y: event.clientY })
  }, [])

  const handleHoverEnd = useCallback(() => {
    setHoveredNode(null)
  }, [])

  const handleNavigate = useCallback(
    async (node: GraphNode) => {
      if (!node.iinBin || !isCompanyBin(node.iinBin) || node.type === 'main') return
      onNodeClick?.(node)
      setNavigatingBin(node.iinBin)
      try {
        const created = await lookupCompany(node.name, node.iinBin, false, caseId)
        upsertCase(created)
        const targetId = created.id
        if (!targetId) {
          throw new Error('API не вернул идентификатор дела')
        }
        router.push(`/cases/${targetId}`)
      } catch (e) {
        console.error(e)
        setSelectedNode(node)
        setPopupPosition({ x: 120, y: 120 })
      } finally {
        setNavigatingBin(null)
      }
    },
    [caseId, onNodeClick, router, upsertCase],
  )

  const handleRebuild = async () => {
    setRebuilding(true)
    try {
      await rebuildAffiliateTree(caseId)
      onTreeUpdated?.()
    } finally {
      setRebuilding(false)
    }
  }

  const handleCheckLseg = useCallback(
    (node: GraphNode) => {
      setSelectedNode(null)
      if (caseId) {
        const params = new URLSearchParams({
          tab: 'lseg',
          entity: node.name,
        })
        router.push(`/cases/${caseId}?${params.toString()}`)
        return
      }
      window.open(
        `https://pk.adata.kz/search?q=${encodeURIComponent(node.name)}`,
        '_blank',
        'noopener,noreferrer',
      )
    },
    [caseId, router],
  )

  return (
    <div className="bg-white rounded-xl border border-neutral-200 p-5">
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <div>
          <h3 className="font-semibold text-neutral-900 flex items-center gap-2">
            <GitBranch className="w-5 h-5 text-neutral-600" />
            Дерево связей
          </h3>
          <p className="text-xs text-neutral-500 mt-1">
            Колёсико — масштаб · «Подробнее» на узле — сведения · «± дочерние» — только ветка графа
          </p>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
            <span className="flex items-center gap-1.5 text-[11px] text-neutral-500"><span className="inline-block w-3 h-3 rounded border border-blue-500 bg-blue-700" />Проверяемая компания</span>
            <span className="flex items-center gap-1.5 text-[11px] text-neutral-500"><span className="inline-block w-3 h-3 rounded border border-rose-300 bg-rose-100" />Санкции / бенефициар</span>
            <span className="flex items-center gap-1.5 text-[11px] text-neutral-500"><span className="inline-block w-3 h-3 rounded border border-amber-300 bg-amber-50" />ФЛ / ПЭП</span>
            <span className="flex items-center gap-1.5 text-[11px] text-neutral-500"><span className="inline-block w-3 h-3 rounded border border-orange-400 bg-orange-50" />Нерезидент</span>
            <span className="flex items-center gap-1.5 text-[11px] text-neutral-500"><span className="inline-block w-3 h-3 rounded border border-blue-400 bg-white" />Есть отчёт</span>
            <span className="flex items-center gap-1.5 text-[11px] text-neutral-500"><span className="inline-block w-3 h-3 rounded border border-neutral-300 bg-neutral-100" />Прочие</span>
          </div>
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
        <div className="flex items-center gap-4 text-sm text-blue-800 bg-blue-50 border border-blue-100 rounded-lg px-4 py-3 mb-4">
          <Image
            src="/loading.gif"
            alt=""
            width={56}
            height={56}
            unoptimized
            className="shrink-0 rounded"
          />
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

      {root && visibleRoot ? (
        <>
          <FlowCanvas
            root={visibleRoot}
            fullRoot={root}
            expandedIds={expandedIds}
            onToggleExpand={handleToggleExpand}
            onSelect={handleSelect}
            onHover={handleHover}
            onHoverEnd={handleHoverEnd}
            hiddenTotal={hiddenTotal}
          />
        </>
      ) : isBuilding || treeStatus === 'pending' ? (
        <LoadingGif
          message={isBuilding ? 'Строим дерево связей…' : 'Дерево связей скоро построится…'}
          size={140}
          className="py-12"
        />
      ) : (
        <p className="text-sm text-neutral-500 py-8 text-center">
          {source === 'adata'
            ? 'Связи не найдены или дерево ещё не готово.'
            : 'Нет данных Adata для дерева.'}
        </p>
      )}

      {isReady && affiliateTree && (
        <p className="text-xs text-neutral-400 mt-3">
          Узлов: {affiliateTree.nodesCount}
          {affiliateTree.builtAt &&
            ` · обновлено ${new Date(affiliateTree.builtAt).toLocaleString('ru-RU')}`}
        </p>
      )}

      <p className="text-xs text-neutral-400 mt-2">
        Наведите на узел для подсказки. Клик по узлу открывает карточку; дочерние — кнопкой «+ раскрыть»
        {navigatingBin ? ` (загрузка ${navigatingBin}…)` : ''}.
      </p>

      {hoveredNode && !selectedNode && (
        <NodeTooltip node={hoveredNode} position={tooltipPosition} />
      )}

      {selectedNode && !showFullReport && (
        <NodePopup
          node={selectedNode}
          position={popupPosition}
          onClose={() => setSelectedNode(null)}
          onViewFull={() => setShowFullReport(true)}
          onCheckLseg={() => handleCheckLseg(selectedNode)}
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
