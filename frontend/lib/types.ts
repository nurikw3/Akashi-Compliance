export type DataSourceKind = 'adata' | 'stub' | 'lseg' | 'none'

export type DataSources = {
  companyInfo: DataSourceKind
  taxes: DataSourceKind
  courts: DataSourceKind
  sanctions: DataSourceKind
  affiliates: DataSourceKind
  graph: DataSourceKind
  assessment: DataSourceKind
  conclusion: DataSourceKind
}

export interface ScoreMetric {
  metric: string
  points: number
  max_points: number
  reason: string
  source: 'adata' | 'lseg' | 'affiliate_tree' | 'none'
}

export interface LsegSanctionHit {
  resultId: string
  primaryName: string
  matchStrength?: string
  matchScore?: number
  submittedName?: string
  categories: string[]
  sources?: string[]
  sanctionLists?: string[]
  rawSources?: string[]
  isSanction: boolean
  isPep: boolean
  countries?: string[]
  countryNames?: string[]
  nationalities?: string[]
  aliases?: string[]
  sourceCategories?: string[]
}

export interface LsegExtendedEntity {
  name: string
  entityType: string
  role?: string
  country?: string
  isOnSanctionList: boolean
  sanctionLists?: string[]
  hits: LsegSanctionHit[]
}

export interface LsegMediaArticle {
  articleId: string
  headline: string
  publicationDate: string
  url: string
  risk: 'HIGH' | 'MEDIUM' | 'LOW' | ''
  categories: string[]
}

export interface LsegData {
  caseSystemId: string
  screenedAt: string
  wc1Rating: string
  screenedName?: string
  screenedIin?: string
  sanctions: {
    isOnList: boolean
    isFormalSanction?: boolean
    hasWatchlistHits?: boolean
    matchedLists: string[]
    hits: LsegSanctionHit[]
  }
  pep: {
    isHit: boolean
    individuals: LsegSanctionHit[]
  }
  adverseMedia: {
    articles: LsegMediaArticle[]
    negativeCount: number
  }
}

export interface AffiliateTreeNode {
  id: string
  name: string
  type: 'main' | 'company' | 'person'
  level: number
  role?: string
  iinBin?: string
  probeError?: string
  hasReport?: boolean
  children: AffiliateTreeNode[]
}

export interface NodeReport {
  source: 'main' | 'cache' | 'case'
  bin: string
  name: string
  caseId?: string
  openCaseId?: string | null
  enrichment?: EnrichmentData
  assessment?: Assessment
  dataSources?: DataSources
  riskLevel?: string | null
  conclusion?: string
  cachedAt?: string
}

export interface AffiliateTree {
  status: 'pending' | 'building' | 'ready' | 'error'
  depth: number
  nodesCount: number
  checkedBins?: string[]
  builtAt?: string | null
  error?: string | null
  root: AffiliateTreeNode | null
}

export interface IndividualCourtCase {
  number: string
  result: string
  type: string
  date: string
  court: string
  category: string
  judge: string
  status?: string
  role?: string
  defendants: string[]
  plaintiffs: string[]
  documents?: Array<{ file_name?: string | null; doc_link?: string | null }>
  history: Array<{
    event_date: string
    name: string
    documents?: Array<{ file_name: string; doc_link: string }>
  }>
}

export interface IndividualCourtsMeta {
  name: string
  role?: string
  companyName?: string
}

export interface VerificationLogEvent {
  ts: string
  provider: string
  action: string
  subject?: {
    type?: string
    value?: string
    name?: string
  }
  request?: {
    endpoint?: string
    params?: Record<string, unknown>
  }
  outcome?: {
    status?: 'ok' | 'error'
    cached?: boolean
    counts?: Record<string, number | boolean>
    message?: string
    meta?: Record<string, unknown>
  }
}

export interface Case {
  id: string
  name: string
  iinBin: string
  status: 'pending' | 'enriching' | 'ready' | 'error'
  riskLevel: 'low' | 'medium' | 'high' | null
  createdAt: Date
  enrichment?: EnrichmentData
  assessment?: Assessment
  affiliateTree?: AffiliateTree
  documents: Document[]
  chatHistory: ChatMessage[]
  conclusion?: string
  sources?: string[]
  dataSources?: DataSources
  /** Set when the case was opened from another case's affiliate graph. */
  parentCaseId?: string | null
  lseg?: LsegData | null
  lsegExtended?: Record<string, LsegExtendedEntity> | null
  scoreBreakdown?: ScoreMetric[] | null
  totalScore?: number | null
  affiliateProfiles?: Record<string, { courts?: EnrichmentData['courts'] }>
  beneficiary?: Record<string, unknown>[]
  individualCourts?: Record<string, IndividualCourtCase[]>
  individualCourtsMeta?: Record<string, IndividualCourtsMeta>
  companyCourtCases?: IndividualCourtCase[]
  verificationLog?: VerificationLogEvent[]
  hasFullReport?: boolean
  fullReportGeneratedAt?: string | null
  fullReportStatus?: 'generating' | null
  fullReportStale?: boolean
  fullReportStaleReason?: string | null
  fullReportStaleMessage?: string | null
  graphBuiltAt?: string | null
  fullReportContextEstimate?: FullReportContextEstimate | null
}

export interface FullReportContextEstimate {
  model: string
  contextWindowTokens: number
  sectionCalls: number
  approxTotalInputTokens: number
  headroomTokens: number
  note: string
  sections: Record<
    string,
    { chars: number; capChars: number; approxTokens: number }
  >
}

export interface EnrichmentData {
  companyInfo: {
    fullName: string
    registrationDate: string
    address: string
    director: string
    director_iin?: string
    employees: number
    industry: string
    legalForm?: string | null
    ownership?: string | null
    sourceLink?: string | null
    operatingStatus?: string | null
  }
  statusFlags?: string[]
  riskFlags?: string[]
  taxes: {
    debt: number
    lastPayment: string
    status: 'clean' | 'debt' | 'critical'
    totalPaid?: number | null
    yearlyPayments?: { year: number; amount: number }[]
  }
  contacts?: {
    phones: string[]
    emails: string[]
    websites: string[]
  }
  requisites?: Record<string, string | number>
  courts: {
    activeCases: number
    completedCases: number
    totalAmount: number
    cases: {
      type: string
      amount: number
      date: string
      status: string
      aiAnalysis?: {
        category: 'criminal' | 'civil' | 'administrative' | 'enforcement'
        severity: 'critical' | 'high' | 'medium' | 'low'
        outcome: 'convicted' | 'pending' | 'dismissed' | 'unknown'
        amount_kzt: number
        summary_ru: string
      } | null
    }[]
    scope?: 'company' | 'director'
    note?: string | null
  }
  sanctions: {
    isOnList: boolean
    lists: string[]
    statusFlags?: string[]
    riskFlags?: string[]
  }
  affiliates: {
    companies: { name: string; iinBin: string; role: string }[]
    individuals: { name: string; iin: string; role: string }[]
  }
}

export interface Assessment {
  riskLevel: 'low' | 'medium' | 'high'
  summary: string
  recommendations: string[]
  flags: { type: 'warning' | 'danger' | 'info'; message: string }[]
}

export interface Document {
  id: string
  filename: string
  fileType: string
  uploadedAt: Date
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: Date
}
