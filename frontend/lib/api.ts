import type { Case, ChatMessage, Document, NodeReport } from '@/lib/types'
import { getAuthHeader } from '@/lib/auth'

/** Browser uses Next rewrite to avoid CORS when dev server port != 3000. */
const API_URL =
  typeof window !== 'undefined'
    ? '/backend-api'
    : process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

type ApiCase = Omit<Case, 'createdAt' | 'documents' | 'chatHistory'> & {
  createdAt: string
  documents?: ApiDocument[]
  chatHistory?: ApiChatMessage[]
}

type ApiDocument = Omit<Document, 'uploadedAt'> & { uploadedAt: string }
type ApiChatMessage = Omit<ChatMessage, 'createdAt'> & { createdAt: string }

function parseCase(raw: ApiCase): Case {
  return {
    ...raw,
    createdAt: new Date(raw.createdAt),
    documents: (raw.documents || []).map((d) => ({
      ...d,
      uploadedAt: new Date(d.uploadedAt),
    })),
    chatHistory: (raw.chatHistory || []).map((m) => ({
      ...m,
      createdAt: new Date(m.createdAt),
    })),
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = typeof FormData !== 'undefined' && init?.body instanceof FormData
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...getAuthHeader(),
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...init?.headers,
    },
  })
  if (response.status === 401) {
    throw new Error('Unauthorized')
  }
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `API error ${response.status}`)
  }
  return response.json() as Promise<T>
}

export async function fetchCases(): Promise<Case[]> {
  const data = await request<ApiCase[]>('/api/cases')
  return data.map(parseCase)
}

export async function fetchCase(id: string): Promise<Case> {
  const data = await request<ApiCase>(`/api/cases/${id}`)
  return parseCase(data)
}

export type ImportPreviewRow = {
  name: string
  iinBin: string
  extraData: Record<string, string>
  valid: boolean
  error?: string
}

export async function parseImportFile(file: File): Promise<ImportPreviewRow[]> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_URL}/api/upload/parse`, {
    method: 'POST',
    headers: getAuthHeader(),
    body: formData,
  })
  if (response.status === 401) {
    throw new Error('Unauthorized')
  }
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `API error ${response.status}`)
  }
  const data = (await response.json()) as { rows: ImportPreviewRow[] }
  return data.rows
}

export async function parseBinsText(text: string): Promise<ImportPreviewRow[]> {
  const data = await request<{ rows: ImportPreviewRow[] }>('/api/upload/parse-bins', {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
  return data.rows
}

/** Client-side BIN list parsing (works without API). */
export function parseBinsLocally(text: string): ImportPreviewRow[] {
  const seen = new Set<string>()
  const rows: ImportPreviewRow[] = []
  for (const match of text.matchAll(/\b(\d{12})\b/g)) {
    const iinBin = match[1]
    if (seen.has(iinBin)) continue
    seen.add(iinBin)
    rows.push({
      name: `БИН ${iinBin}`,
      iinBin,
      extraData: {},
      valid: true,
    })
  }
  return rows
}

export type DuplicateMatch = {
  iinBin: string
  existingCaseId: string
  name: string
  status: string
  riskLevel: string | null
}

export async function checkUploadDuplicates(
  iinBins: string[]
): Promise<{ matches: DuplicateMatch[]; count: number }> {
  return request('/api/upload/check-duplicates', {
    method: 'POST',
    body: JSON.stringify({ iinBins }),
  })
}

export type UploadCasesResult = {
  cases: Case[]
  created: number
  skipped: number
  refreshed: number
}

export async function uploadCases(
  cases: { name: string; iinBin: string }[],
  onDuplicate: 'create' | 'skip' | 'refresh' = 'create'
): Promise<UploadCasesResult> {
  const data = await request<{
    cases: ApiCase[]
    created: number
    skipped: number
    refreshed: number
  }>('/api/upload', {
    method: 'POST',
    body: JSON.stringify({ cases, onDuplicate }),
  })
  return {
    cases: data.cases.map(parseCase),
    created: data.created ?? 0,
    skipped: data.skipped ?? 0,
    refreshed: data.refreshed ?? 0,
  }
}

export type AiStatus = {
  openaiConfigured: boolean
  model: string | null
}

export async function fetchAiStatus(): Promise<AiStatus> {
  return request<AiStatus>('/api/ai/status')
}

export async function sendChatMessage(
  caseId: string,
  message: string
): Promise<{
  status: string
  userMessage: ChatMessage
  job?: { mode: string; queue: string }
}> {
  const data = await request<{
    status: string
    userMessage: ApiChatMessage
    job?: { mode: string; queue: string }
  }>(`/api/cases/${caseId}/chat`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  })
  return {
    status: data.status,
    job: data.job,
    userMessage: {
      ...data.userMessage,
      createdAt: new Date(data.userMessage.createdAt),
    },
  }
}

export function caseReportPdfUrl(caseId: string): string {
  return `${API_URL}/api/cases/${caseId}/report`
}

export async function downloadCaseReport(caseId: string, filename: string): Promise<void> {
  const response = await fetch(caseReportPdfUrl(caseId), {
    headers: getAuthHeader(),
  })
  if (response.status === 401) {
    throw new Error('Unauthorized')
  }
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Не удалось скачать отчёт (${response.status})`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export async function uploadDocument(
  caseId: string,
  filename: string,
  fileType: string
): Promise<Document> {
  const data = await request<{ document: ApiDocument }>(
    `/api/cases/${caseId}/documents`,
    {
      method: 'POST',
      body: JSON.stringify({ filename, fileType }),
    }
  )
  return {
    ...data.document,
    uploadedAt: new Date(data.document.uploadedAt),
  }
}

export async function fetchNodeReport(
  caseId: string,
  iinBin: string
): Promise<NodeReport> {
  const params = new URLSearchParams({ iinBin })
  return request<NodeReport>(`/api/cases/${caseId}/node-report?${params}`)
}

/** Background lookup — do not use for modal; prefer fetchNodeReport. */
export async function lookupCompany(
  name: string,
  iinBin: string,
  sync = false,
  parentCaseId?: string
): Promise<Case> {
  const data = await request<ApiCase>('/api/lookup', {
    method: 'POST',
    body: JSON.stringify({ name, iinBin, sync, parentCaseId }),
  })
  return parseCase(data)
}

export async function rebuildAffiliateTree(
  caseId: string
): Promise<{ status: string; message: string }> {
  return request(`/api/cases/${caseId}/graph/build`, { method: 'POST' })
}

export async function checkHealth(): Promise<boolean> {
  try {
    await request<{ status: string }>('/health')
    return true
  } catch {
    return false
  }
}

export async function rescreenAllWithLseg(
  force = true
): Promise<{ queued: number; message: string; force?: boolean }> {
  const q = force ? '?force=true' : ''
  return request(`/api/admin/rescreen${q}`, { method: 'POST' })
}

export async function rescreenCaseLseg(
  caseId: string,
  force = true
): Promise<{
  caseId: string
  riskLevel: string | null
  totalScore: number | null
  lseg: Case['lseg']
}> {
  const q = force ? '?force=true' : ''
  return request(`/api/cases/${caseId}/lseg/rescreen${q}`, { method: 'POST' })
}

export async function fetchFullReport(
  caseId: string
): Promise<{ report: string; generatedAt: string | null }> {
  return request(`/api/cases/${caseId}/full-report`)
}

export async function generateFullReport(
  caseId: string
): Promise<{ status: string; message: string; caseId: string }> {
  return request(`/api/cases/${caseId}/full-report`, { method: 'POST' })
}

export async function fetchCaseScore(caseId: string): Promise<{
  totalScore: number | null
  riskLevel: string | null
  breakdown: import('@/lib/types').ScoreMetric[]
  lsegScreenedAt: string | null
}> {
  return request(`/api/cases/${caseId}/score`)
}

export { API_URL }
