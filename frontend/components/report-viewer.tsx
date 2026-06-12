'use client'

import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'
import {
  Shield,
  Scale,
  Building2,
  Database,
  FileText,
  ThumbsUp,
  TriangleAlert,
  Info,
  ExternalLink,
  Gauge,
  UserRound,
  ChevronDown,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Section {
  heading: string
  content: string
}

interface ParsedReport {
  title: string
  intro: string
  sections: Section[]
}

// ─── Parser ───────────────────────────────────────────────────────────────────

function parseReport(markdown: string): ParsedReport {
  const lines = markdown.split('\n')
  let title = ''
  const sections: Section[] = []
  let currentHeading = ''
  let currentContent: string[] = []
  const introLines: string[] = []
  let foundFirstH2 = false

  for (const line of lines) {
    const h1 = line.match(/^# (.+)/)
    const h2 = line.match(/^## (.+)/)

    if (h1) {
      title = h1[1]
    } else if (h2) {
      if (!foundFirstH2) {
        foundFirstH2 = true
      } else {
        sections.push({
          heading: currentHeading,
          content: currentContent.join('\n').trim(),
        })
      }
      currentHeading = h2[1]
      currentContent = []
    } else {
      if (!foundFirstH2) {
        introLines.push(line)
      } else {
        currentContent.push(line)
      }
    }
  }

  if (currentHeading) {
    sections.push({
      heading: currentHeading,
      content: currentContent.join('\n').trim(),
    })
  }

  return { title, intro: introLines.join('\n').trim(), sections }
}

// ─── Section config ───────────────────────────────────────────────────────────

type SectionConfig = {
  icon: React.ReactNode
  borderColor: string
  iconBg: string
  headerBg: string
}

function getSectionConfig(heading: string): SectionConfig {
  const h = heading.toLowerCase()

  if (h.includes('снимок')) {
    return {
      icon: <Gauge className="w-4 h-4" />,
      borderColor: 'border-l-sky-500',
      iconBg: 'bg-sky-50 text-sky-600',
      headerBg: 'bg-sky-50/40',
    }
  }
  if (h.includes('существенн')) {
    return {
      icon: <TriangleAlert className="w-4 h-4" />,
      borderColor: 'border-l-orange-500',
      iconBg: 'bg-orange-50 text-orange-600',
      headerBg: 'bg-orange-50/40',
    }
  }
  if (h.includes('физическ') || h.includes('директор') || h.includes('учредител')) {
    return {
      icon: <UserRound className="w-4 h-4" />,
      borderColor: 'border-l-teal-500',
      iconBg: 'bg-teal-50 text-teal-600',
      headerBg: 'bg-teal-50/40',
    }
  }
  if (h.includes('покрыт')) {
    return {
      icon: <Database className="w-4 h-4" />,
      borderColor: 'border-l-neutral-400',
      iconBg: 'bg-neutral-100 text-neutral-500',
      headerBg: 'bg-neutral-50',
    }
  }
  if (h.includes('резюме') || h.includes('executive') || h.includes('итоговый риск')) {
    return {
      icon: <FileText className="w-4 h-4" />,
      borderColor: 'border-l-blue-500',
      iconBg: 'bg-blue-50 text-blue-600',
      headerBg: 'bg-blue-50/40',
    }
  }
  if (h.includes('санкц') || h.includes('lseg')) {
    return {
      icon: <Shield className="w-4 h-4" />,
      borderColor: 'border-l-rose-500',
      iconBg: 'bg-rose-50 text-rose-600',
      headerBg: 'bg-rose-50/40',
    }
  }
  if (h.includes('суд')) {
    return {
      icon: <Scale className="w-4 h-4" />,
      borderColor: 'border-l-amber-500',
      iconBg: 'bg-amber-50 text-amber-600',
      headerBg: 'bg-amber-50/40',
    }
  }
  if (h.includes('структур') || h.includes('аффил') || h.includes('бенеф')) {
    return {
      icon: <Building2 className="w-4 h-4" />,
      borderColor: 'border-l-violet-500',
      iconBg: 'bg-violet-50 text-violet-600',
      headerBg: 'bg-violet-50/40',
    }
  }
  if (h.includes('рекомендац')) {
    return {
      icon: <ThumbsUp className="w-4 h-4" />,
      borderColor: 'border-l-emerald-500',
      iconBg: 'bg-emerald-50 text-emerald-600',
      headerBg: 'bg-emerald-50/40',
    }
  }
  if (h.includes('матриц') || h.includes('риск')) {
    return {
      icon: <TriangleAlert className="w-4 h-4" />,
      borderColor: 'border-l-orange-500',
      iconBg: 'bg-orange-50 text-orange-600',
      headerBg: 'bg-orange-50/40',
    }
  }
  if (h.includes('источник') || h.includes('данн')) {
    return {
      icon: <Database className="w-4 h-4" />,
      borderColor: 'border-l-neutral-400',
      iconBg: 'bg-neutral-100 text-neutral-500',
      headerBg: 'bg-neutral-50',
    }
  }

  return {
    icon: <Info className="w-4 h-4" />,
    borderColor: 'border-l-neutral-300',
    iconBg: 'bg-neutral-100 text-neutral-500',
    headerBg: 'bg-neutral-50',
  }
}

// ─── Pre-processors ───────────────────────────────────────────────────────────

/**
 * Wrap "### Краткое сведение" / "### Вердикт ИИ" blocks in a blockquote so
 * the blockquote component can render them as a highlighted summary card.
 */
function wrapTakeawayBlocks(text: string): string {
  const lines = text.split('\n')
  const result: string[] = []
  let inTakeaway = false
  let trailingEmpty = 0

  for (const line of lines) {
    const isTakeawayHeading = /^###\s+(Краткое сведение|Вердикт ИИ|Вывод ИИ)/.test(line)
    const isNewSection = /^#{1,2}\s+/.test(line)

    if (isTakeawayHeading) {
      inTakeaway = true
      trailingEmpty = 0
      result.push('> ' + line)
    } else if (inTakeaway) {
      if (isNewSection) {
        inTakeaway = false
        result.push(line)
      } else if (line.trim() === '') {
        trailingEmpty++
        if (trailingEmpty > 1) {
          inTakeaway = false
          result.push(line)
        } else {
          result.push('>')
        }
      } else {
        trailingEmpty = 0
        result.push('> ' + line)
      }
    } else {
      result.push(line)
    }
  }

  return result.join('\n')
}

function processContent(content: string): string {
  return wrapTakeawayBlocks(content)
}

// ─── Markdown renderer ────────────────────────────────────────────────────────

function SectionMarkdown({ content }: { content: string }) {
  const processed = useMemo(() => processContent(content), [content])
  const router = useRouter()

  return (
    <div className="report-section-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h3: ({ children }) => {
            const text = String(children ?? '')
            const isTakeaway = /Краткое сведение|Вердикт ИИ|Вывод ИИ/.test(text)
            if (isTakeaway) {
              return (
                <p className="text-[10.5px] font-bold uppercase tracking-widest text-neutral-400 mb-2 mt-0">
                  {text}
                </p>
              )
            }
            return (
              <h3 className="text-[14px] font-semibold mt-5 mb-2 first:mt-0 text-neutral-800">
                {children}
              </h3>
            )
          },
          h4: ({ children }) => (
            <h4 className="text-xs font-semibold mt-4 mb-1.5 text-neutral-500 uppercase tracking-wide">
              {children}
            </h4>
          ),
          p: ({ children }) => (
            <p className="text-[14px] leading-[1.8] text-neutral-700 mb-3 last:mb-0">
              {children}
            </p>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-neutral-900">{children}</strong>
          ),
          em: ({ children }) => (
            <em className="italic text-neutral-600">{children}</em>
          ),
          ul: ({ children }) => (
            <ul className="list-disc pl-5 mb-3 space-y-1.5 text-[14px] text-neutral-700 last:mb-0">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-5 mb-3 space-y-1.5 text-[14px] text-neutral-700 last:mb-0">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="leading-relaxed">{children}</li>
          ),
          hr: () => <hr className="my-5 border-neutral-100" />,
          blockquote: ({ children }) => (
            <div className="mt-5 mb-1 rounded-lg border border-neutral-200 bg-neutral-50 px-4 py-3.5 space-y-0.5">
              {children}
            </div>
          ),
          a: ({ href, children }) => {
            if (href?.startsWith('/cases/')) {
              return (
                <button
                  onClick={() => router.push(href)}
                  className="inline-flex items-center gap-1 text-violet-700 font-medium text-[13px] hover:text-violet-900 hover:underline underline-offset-2 transition-colors"
                >
                  {children}
                  <ExternalLink className="w-3 h-3 opacity-60" />
                </button>
              )
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 underline underline-offset-2 hover:text-blue-800 break-all"
              >
                {children}
              </a>
            )
          },
          table: ({ children }) => (
            <div className="my-4 overflow-x-auto rounded-lg border border-neutral-200 text-[13px]">
              <table className="min-w-full border-collapse">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-neutral-50 border-b border-neutral-200">{children}</thead>
          ),
          th: ({ children }) => (
            <th className="px-3 py-2 text-left text-xs font-semibold text-neutral-600 whitespace-nowrap">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2.5 text-neutral-700 border-b border-neutral-100 align-top max-w-xs break-words">
              {children}
            </td>
          ),
          tr: ({ children }) => (
            <tr className="hover:bg-neutral-50/60 transition-colors">{children}</tr>
          ),
          code: ({ className: codeClass, children }) => {
            if (codeClass) {
              return (
                <code className="block overflow-x-auto rounded-lg p-3 text-xs font-mono my-2 bg-neutral-100 text-neutral-800">
                  {children}
                </code>
              )
            }
            return (
              <code className="rounded px-1.5 py-0.5 text-xs font-mono bg-neutral-100 text-neutral-800">
                {children}
              </code>
            )
          },
          pre: ({ children }) => <pre className="my-2">{children}</pre>,
        }}
      >
        {processed}
      </ReactMarkdown>
    </div>
  )
}

// ─── Section card ─────────────────────────────────────────────────────────────

function SectionCard({
  section,
  collapsed,
  onToggle,
}: {
  section: Section
  collapsed: boolean
  onToggle: () => void
}) {
  if (!section.content.trim() && !section.heading) return null
  const config = getSectionConfig(section.heading)

  return (
    <div className="rounded-xl border border-neutral-200 bg-white overflow-hidden shadow-sm">
      {section.heading && (
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          className="w-full flex items-center gap-2.5 px-5 py-3 text-left transition-colors bg-[#263246] hover:bg-[#2e3c54]"
        >
          <span className="p-1.5 rounded-md bg-white/15 text-white">
            {config.icon}
          </span>
          <h2 className="text-[14.5px] font-semibold text-white flex-1 uppercase tracking-wide">{section.heading}</h2>
          <ChevronDown
            className={cn(
              'w-4 h-4 text-white/70 transition-transform shrink-0',
              collapsed && '-rotate-90',
            )}
          />
        </button>
      )}
      {section.content && !collapsed && (
        <div className="px-5 py-4">
          <SectionMarkdown content={section.content} />
        </div>
      )}
    </div>
  )
}

// ─── Public component ─────────────────────────────────────────────────────────

/** Long list-heavy / reference sections start collapsed to tame the wall of text. */
const DEFAULT_COLLAPSED_KEYWORDS = ['структур', 'покрыт', 'ссылк', 'расшифров', 'сокращ']

function defaultCollapsedSet(sections: Section[]): Set<number> {
  const collapsed = new Set<number>()
  sections.forEach((section, i) => {
    const h = section.heading.toLowerCase()
    if (DEFAULT_COLLAPSED_KEYWORDS.some((kw) => h.includes(kw))) collapsed.add(i)
  })
  return collapsed
}

export function ReportViewer({ markdown }: { markdown: string }) {
  const parsed = useMemo(() => parseReport(markdown), [markdown])
  const [collapsed, setCollapsed] = useState<Set<number>>(() =>
    defaultCollapsedSet(parsed.sections),
  )

  const toggle = (i: number) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })

  const allCollapsed =
    parsed.sections.length > 0 && collapsed.size === parsed.sections.length
  const setAll = (collapse: boolean) =>
    setCollapsed(collapse ? new Set(parsed.sections.map((_, i) => i)) : new Set())

  return (
    <div className="space-y-4">
      {parsed.intro && (
        <div className="rounded-xl border border-neutral-200 bg-white px-5 py-4 shadow-sm">
          <SectionMarkdown content={parsed.intro} />
        </div>
      )}
      {parsed.sections.length > 1 && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => setAll(!allCollapsed)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-neutral-500 hover:text-neutral-800 transition-colors px-2.5 py-1 rounded-md hover:bg-neutral-100"
          >
            <ChevronDown
              className={cn('w-3.5 h-3.5 transition-transform', allCollapsed && '-rotate-90')}
            />
            {allCollapsed ? 'Развернуть всё' : 'Свернуть всё'}
          </button>
        </div>
      )}
      {parsed.sections.map((section, i) => (
        <SectionCard
          key={i}
          section={section}
          collapsed={collapsed.has(i)}
          onToggle={() => toggle(i)}
        />
      ))}
    </div>
  )
}
