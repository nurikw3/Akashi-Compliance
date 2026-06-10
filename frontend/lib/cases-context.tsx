'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import * as api from '@/lib/api'
import { initialMockCases } from '@/lib/mock-data'
import type { UploadCasesResult } from '@/lib/api'
import type { Case, ChatMessage, Document } from '@/lib/types'

interface CasesContextType {
  cases: Case[]
  apiConnected: boolean
  addCases: (
    newCases: { name: string; iinBin: string; extraData?: Record<string, string> }[],
    options?: { onDuplicate?: 'create' | 'skip' | 'refresh' }
  ) => Promise<UploadCasesResult | void>
  getCase: (id: string) => Case | undefined
  addChatMessage: (caseId: string, message: string) => Promise<void>
  addDocument: (caseId: string, filename: string, fileType: string) => Promise<void>
  refreshCase: (id: string) => Promise<Case | null>
  upsertCase: (item: Case) => void
}

const CasesContext = createContext<CasesContextType | null>(null)

export function CasesProvider({ children }: { children: ReactNode }) {
  const [cases, setCases] = useState<Case[]>([])
  const [apiConnected, setApiConnected] = useState(false)
  const pollingRef = useRef<Set<string>>(new Set())

  const upsertCase = useCallback((item: Case) => {
    setCases((prev) => {
      if (prev.some((c) => c.id === item.id)) {
        return prev.map((c) => (c.id === item.id ? item : c))
      }
      return [item, ...prev]
    })
  }, [])

  const refreshCase = useCallback(async (id: string): Promise<Case | null> => {
    try {
      const updated = await api.fetchCase(id)
      setCases((prev) => {
        if (prev.some((c) => c.id === id)) {
          return prev.map((c) => (c.id === id ? updated : c))
        }
        return [updated, ...prev]
      })
      return updated
    } catch {
      return null
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function load() {
      const ok = await api.checkHealth()
      if (cancelled) return
      setApiConnected(ok)
      if (ok) {
        try {
          const data = await api.fetchCases()
          if (!cancelled) setCases(data)
        } catch {
          if (!cancelled) setCases(initialMockCases)
        }
      } else {
        setCases(initialMockCases)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!apiConnected) return

    const enriching = cases.filter((c) => c.status === 'enriching' || c.status === 'pending')
    const buildingTree = cases.filter((c) => c.affiliateTree?.status === 'building')
    const awaitingConclusion = cases.filter(
      (c) => c.status === 'ready' && c.enrichment && !c.conclusion
    )
    const awaitingChat = cases.filter((c) =>
      c.chatHistory.some((m) => m.role === 'user') &&
      (c.chatHistory.length === 0 ||
        c.chatHistory[c.chatHistory.length - 1]?.role === 'user')
    )
    const pollTargets = new Map<string, Case>()
    for (const c of [
      ...enriching,
      ...buildingTree,
      ...awaitingConclusion,
      ...awaitingChat,
    ]) {
      pollTargets.set(c.id, c)
    }
    const toPoll = [...pollTargets.values()]
    if (toPoll.length === 0) return

    const interval = setInterval(async () => {
      for (const c of toPoll) {
        if (pollingRef.current.has(c.id)) continue
        pollingRef.current.add(c.id)
        try {
          await refreshCase(c.id)
        } catch {
          /* ignore transient errors */
        } finally {
          pollingRef.current.delete(c.id)
        }
      }
    }, 2500)

    return () => clearInterval(interval)
  }, [cases, apiConnected, refreshCase])

  const mergeUploadedCases = useCallback((uploaded: Case[]) => {
    setCases((prev) => {
      const next = [...prev]
      for (const item of uploaded) {
        const idx = next.findIndex((c) => c.id === item.id)
        if (idx >= 0) next[idx] = item
        else next.unshift(item)
      }
      return next
    })
  }, [])

  const addCases = useCallback(
    async (
      newCases: { name: string; iinBin: string; extraData?: Record<string, string> }[],
      options?: { onDuplicate?: 'create' | 'skip' | 'refresh' }
    ) => {
      if (!apiConnected) {
        setCases((prev) => [
          ...newCases.map((c, index) => ({
            id: `${Date.now()}-${index}`,
            name: c.name,
            iinBin: c.iinBin,
            status: 'pending' as const,
            createdAt: new Date(),
            documents: [],
            chatHistory: [],
          })),
          ...prev,
        ])
        return
      }

      const result = await api.uploadCases(
        newCases.map((c) => ({ name: c.name, iinBin: c.iinBin })),
        options?.onDuplicate ?? 'create'
      )
      mergeUploadedCases(result.cases)
      return result
    },
    [apiConnected, mergeUploadedCases]
  )

  const getCase = useCallback((id: string) => cases.find((c) => c.id === id), [cases])

  const addChatMessage = useCallback(
    async (caseId: string, message: string) => {
      if (!apiConnected) {
        const reply: ChatMessage = {
          id: `msg-${Date.now()}`,
          role: 'assistant',
          content: 'API недоступен. Подключите backend на порту 8000.',
          createdAt: new Date(),
        }
        setCases((prev) =>
          prev.map((c) =>
            c.id === caseId
              ? {
                  ...c,
                  chatHistory: [
                    ...c.chatHistory,
                    {
                      id: `user-${Date.now()}`,
                      role: 'user',
                      content: message,
                      createdAt: new Date(),
                    },
                    reply,
                  ],
                }
              : c
          )
        )
        return
      }

      const beforeCount =
        cases.find((c) => c.id === caseId)?.chatHistory.length ?? 0
      await api.sendChatMessage(caseId, message)

      try {
        const withUser = await api.fetchCase(caseId)
        setCases((prev) => {
          if (prev.some((c) => c.id === caseId)) {
            return prev.map((c) => (c.id === caseId ? withUser : c))
          }
          return [withUser, ...prev]
        })
      } catch {
        /* ignore */
      }

      for (let attempt = 0; attempt < 90; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000))
        try {
          const updated = await api.fetchCase(caseId)
          setCases((prev) => {
            if (prev.some((c) => c.id === caseId)) {
              return prev.map((c) => (c.id === caseId ? updated : c))
            }
            return [updated, ...prev]
          })
          const last = updated.chatHistory[updated.chatHistory.length - 1]
          if (
            updated.chatHistory.length > beforeCount &&
            last?.role === 'assistant'
          ) {
            break
          }
        } catch {
          /* keep polling */
        }
      }
    },
    [apiConnected, cases]
  )

  const addDocument = useCallback(
    async (caseId: string, filename: string, fileType: string) => {
      if (!apiConnected) {
        const doc: Document = {
          id: `doc-${Date.now()}`,
          filename,
          fileType,
          uploadedAt: new Date(),
        }
        setCases((prev) =>
          prev.map((c) =>
            c.id === caseId ? { ...c, documents: [...c.documents, doc] } : c
          )
        )
        return
      }

      const doc = await api.uploadDocument(caseId, filename, fileType)
      setCases((prev) =>
        prev.map((c) =>
          c.id === caseId ? { ...c, documents: [...c.documents, doc] } : c
        )
      )
    },
    [apiConnected]
  )

  return (
    <CasesContext.Provider
      value={{
        cases,
        apiConnected,
        addCases,
        getCase,
        addChatMessage,
        addDocument,
        refreshCase,
        upsertCase,
      }}
    >
      {children}
    </CasesContext.Provider>
  )
}

export function useCases() {
  const context = useContext(CasesContext)
  if (!context) throw new Error('useCases must be used within CasesProvider')
  return context
}
