import type { Case } from '@/lib/types'

const PLACEHOLDER_NAME = /^(бин|иин)\s*\d{12}$/i

export function formatPersonField(value: unknown): string {
  if (value == null || value === '') return '—'
  if (typeof value === 'string') {
    const text = value.trim()
    if (!text || text === '—') return '—'
    if (text.startsWith('{') || text.startsWith('[')) return '—'
    return text
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    for (const key of ['fullname_director', 'fullName', 'name', 'fio', 'director_name']) {
      const nested = record[key]
      if (typeof nested === 'string' && nested.trim()) return nested.trim()
    }
    return '—'
  }
  return String(value)
}

export function caseDisplayName(caseData: Pick<Case, 'name' | 'iinBin' | 'enrichment'>): string {
  const fromEnrichment = caseData.enrichment?.companyInfo?.fullName?.trim()
  if (fromEnrichment && fromEnrichment !== '—') {
    return fromEnrichment
  }
  const name = caseData.name?.trim() ?? ''
  if (name && !PLACEHOLDER_NAME.test(name) && name !== caseData.iinBin) {
    return name
  }
  return fromEnrichment || name || `БИН ${caseData.iinBin}`
}

/** Имя PDF-файла вида `Название_ИИН.pdf` (чистит недопустимые в именах символы). */
export function pdfFileName(name: string, iin?: string, fallbackId = ''): string {
  const safe = (name || '')
    .replace(/[\/\\:*?"<>|«»“”'`]+/g, '')
    .replace(/\s+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, 80)
  const id = (iin || fallbackId || '').trim()
  return safe ? `${safe}_${id}.pdf` : `${id || 'report'}.pdf`
}
