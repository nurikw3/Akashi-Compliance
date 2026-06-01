import type { AffiliateTreeNode, Case } from '@/lib/types'

export type CaseGroup = {
  id: string
  primary: Case
  related: Case[]
  totalCount: number
}

function normalizeBin(value: string | undefined): string | null {
  if (!value) return null
  const digits = value.replace(/\D/g, '')
  return digits.length === 12 ? digits : null
}

function collectBinsFromTree(node: AffiliateTreeNode | null | undefined): Set<string> {
  const bins = new Set<string>()
  if (!node) return bins

  const walk = (n: AffiliateTreeNode) => {
    const bin = normalizeBin(n.iinBin)
    if (bin) bins.add(bin)
    for (const child of n.children) walk(child)
  }
  walk(node)
  return bins
}

/** Prefer original upload (oldest, no parent) when several cases share a BIN. */
function pickCanonicalCaseForBin(a: Case, b: Case): Case {
  const aFromGraph = Boolean(a.parentCaseId)
  const bFromGraph = Boolean(b.parentCaseId)
  if (aFromGraph !== bFromGraph) return aFromGraph ? b : a

  const aTime = a.createdAt.getTime()
  const bTime = b.createdAt.getTime()
  if (aTime !== bTime) return aTime < bTime ? a : b

  return a
}

/** One row per BIN — keep the earliest / originally uploaded case. */
export function dedupeCasesByBin(cases: Case[]): Case[] {
  const byBin = new Map<string, Case>()
  for (const c of cases) {
    const bin = normalizeBin(c.iinBin)
    if (!bin) continue
    const existing = byBin.get(bin)
    if (!existing) {
      byBin.set(bin, c)
      continue
    }
    byBin.set(bin, pickCanonicalCaseForBin(existing, c))
  }
  return [...byBin.values()]
}

/**
 * Root = first uploaded on the site (oldest createdAt among top-level cases).
 * Cases opened later from the graph (parentCaseId) are never roots.
 */
function pickPrimary(cases: Case[]): Case {
  const caseIds = new Set(cases.map((c) => c.id))

  const topLevel = cases.filter(
    (c) => !c.parentCaseId || !caseIds.has(c.parentCaseId),
  )
  const pool = topLevel.length > 0 ? topLevel : cases

  return [...pool].sort(
    (a, b) => a.createdAt.getTime() - b.createdAt.getTime(),
  )[0]
}

class UnionFind {
  parent: number[]

  constructor(size: number) {
    this.parent = Array.from({ length: size }, (_, i) => i)
  }

  find(i: number): number {
    if (this.parent[i] !== i) {
      this.parent[i] = this.find(this.parent[i])
    }
    return this.parent[i]
  }

  union(a: number, b: number) {
    const ra = this.find(a)
    const rb = this.find(b)
    if (ra !== rb) this.parent[rb] = ra
  }
}

/**
 * Group cases that belong to the same affiliate graph (shared BINs in trees or parentCaseId).
 */
export function buildCaseGroups(cases: Case[]): CaseGroup[] {
  if (cases.length === 0) return []

  const unique = dedupeCasesByBin(cases)
  const indexById = new Map(unique.map((c, i) => [c.id, i]))
  const uf = new UnionFind(unique.length)

  const binToIndices = new Map<string, number[]>()
  unique.forEach((c, i) => {
    const bin = normalizeBin(c.iinBin)
    if (!bin) return
    const list = binToIndices.get(bin) || []
    list.push(i)
    binToIndices.set(bin, list)
  })

  for (const c of unique) {
    const i = indexById.get(c.id)
    if (i === undefined) continue

    if (c.parentCaseId) {
      const parentIdx = indexById.get(c.parentCaseId)
      if (parentIdx !== undefined) uf.union(i, parentIdx)
    }

    const treeBins = collectBinsFromTree(c.affiliateTree?.root)
    treeBins.add(normalizeBin(c.iinBin) || '')
    const linked = new Set<number>([i])
    for (const bin of treeBins) {
      if (!bin) continue
      for (const j of binToIndices.get(bin) || []) linked.add(j)
    }
    const arr = [...linked]
    for (let k = 1; k < arr.length; k += 1) uf.union(arr[0], arr[k])
  }

  const buckets = new Map<number, Case[]>()
  unique.forEach((c, i) => {
    const root = uf.find(i)
    const list = buckets.get(root) || []
    list.push(c)
    buckets.set(root, list)
  })

  return [...buckets.values()]
    .map((group) => {
      const primary = pickPrimary(group)
      const related = group
        .filter((c) => c.id !== primary.id)
        .sort((a, b) => {
          const aChild = a.parentCaseId === primary.id ? 0 : 1
          const bChild = b.parentCaseId === primary.id ? 0 : 1
          if (aChild !== bChild) return aChild - bChild
          return a.createdAt.getTime() - b.createdAt.getTime()
        })
      return {
        id: primary.id,
        primary,
        related,
        totalCount: group.length,
      }
    })
    .sort((a, b) => a.primary.createdAt.getTime() - b.primary.createdAt.getTime())
}
