import type { DataSourceKind, DataSources, VerificationLogEvent } from '@/lib/types'

export interface SourceInfo {
  provider: string // human label, e.g. "Adata", "LSEG", "—"
  endpoint?: string // e.g. "/company/info"
  url?: string // public source URL, e.g. https://pk.adata.kz/company/{bin}
}

/** Public Adata company page for a 12-digit BIN/IIN. */
export function adataCompanyUrl(bin?: string | null): string | undefined {
  const digits = String(bin ?? '').replace(/\D/g, '')
  return digits.length === 12 ? `https://pk.adata.kz/company/${digits}` : undefined
}

const PROVIDER_LABEL: Record<DataSourceKind, string> = {
  adata: 'Adata',
  lseg: 'LSEG',
  stub: '—',
  none: '—',
}

// Substrings that tie a UI section to a verification-log endpoint/action.
const SECTION_ENDPOINT_HINTS: Partial<Record<keyof DataSources, string[]>> = {
  companyInfo: ['/company/info', '/company/basic'],
  taxes: ['/company/info', 'riskfactor'],
  courts: ['/courtcase', 'court', '/individual'],
  sanctions: ['screen', 'lseg', 'world-check'],
  affiliates: ['/relation', 'beneficiary', 'connectedDiagram'],
  graph: ['/relation', 'affiliate'],
}

/** Resolve the provider + representative endpoint for a section. */
export function resolveSectionSource(
  dataSources: DataSources | undefined,
  verificationLog: VerificationLogEvent[] | undefined,
  section: keyof DataSources,
  companyBin?: string | null,
): SourceInfo {
  const kind: DataSourceKind = dataSources?.[section] ?? 'none'
  const provider = PROVIDER_LABEL[kind === 'stub' ? 'none' : kind]
  if (provider === '—') return { provider }

  const hints = SECTION_ENDPOINT_HINTS[section] ?? []
  const endpoint = findEndpoint(verificationLog, hints)
  const bin = companyBin ?? mainBinFromLog(verificationLog)
  const url = kind === 'adata' ? adataCompanyUrl(bin) : undefined
  return { provider, endpoint, url }
}

/** Pick the main company BIN from verification-log subjects (type === "BIN"). */
function mainBinFromLog(log: VerificationLogEvent[] | undefined): string | undefined {
  if (!log) return undefined
  for (const event of log) {
    const subj = event.subject
    if (subj?.type === 'BIN' && subj.value) return subj.value
  }
  return undefined
}

function findEndpoint(
  log: VerificationLogEvent[] | undefined,
  hints: string[],
): string | undefined {
  if (!log || hints.length === 0) return undefined
  for (const event of log) {
    const ep = event.request?.endpoint
    if (!ep) continue
    const hay = `${ep} ${event.action ?? ''}`.toLowerCase()
    if (hints.some((h) => hay.includes(h.toLowerCase()))) return ep
  }
  return undefined
}
