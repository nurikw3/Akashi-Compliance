'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'

type MarkdownContentProps = {
  children: string
  className?: string
  /** Light text on dark backgrounds (e.g. user chat bubble). */
  inverted?: boolean
}

export function MarkdownContent({
  children,
  className,
  inverted = false,
}: MarkdownContentProps) {
  const text = inverted ? 'text-white' : 'text-neutral-700'
  const heading = inverted ? 'text-white' : 'text-neutral-900'
  const muted = inverted ? 'text-white/75' : 'text-neutral-500'
  const border = inverted ? 'border-white/25' : 'border-neutral-200'
  const link = inverted
    ? 'text-blue-100 underline hover:text-white'
    : 'text-blue-600 hover:underline'
  const codeBg = inverted ? 'bg-white/20' : 'bg-neutral-100'
  const tableHeadBg = inverted ? 'bg-white/10' : 'bg-neutral-50'
  const thText = inverted ? 'text-white' : 'text-neutral-900'
  const tdText = inverted ? 'text-white/90' : 'text-neutral-700'
  const tableDivide = inverted ? 'divide-white/15' : 'divide-neutral-200'
  const tdBorder = inverted ? 'border-white/10' : 'border-neutral-100'

  if (!children.trim()) return null

  return (
    <div className={cn('markdown-content max-w-none', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children: c }) => (
            <h1 className={cn('text-xl font-bold mt-4 mb-2 first:mt-0', heading)}>{c}</h1>
          ),
          h2: ({ children: c }) => (
            <h2 className={cn('text-lg font-semibold mt-4 mb-2 first:mt-0', heading)}>{c}</h2>
          ),
          h3: ({ children: c }) => (
            <h3 className={cn('text-base font-semibold mt-3 mb-1.5 first:mt-0', heading)}>{c}</h3>
          ),
          p: ({ children: c }) => (
            <p className={cn('mb-2 last:mb-0 leading-relaxed', text)}>{c}</p>
          ),
          strong: ({ children: c }) => <strong className="font-semibold">{c}</strong>,
          em: ({ children: c }) => <em className="italic">{c}</em>,
          ul: ({ children: c }) => (
            <ul className={cn('list-disc pl-5 mb-2 space-y-1', text)}>{c}</ul>
          ),
          ol: ({ children: c }) => (
            <ol className={cn('list-decimal pl-5 mb-2 space-y-1', text)}>{c}</ol>
          ),
          li: ({ children: c }) => <li className="leading-relaxed">{c}</li>,
          hr: () => <hr className={cn('my-4', border)} />,
          a: ({ href, children: c }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" className={link}>
              {c}
            </a>
          ),
          blockquote: ({ children: c }) => (
            <blockquote className={cn('border-l-4 pl-3 my-2 italic', border, muted)}>
              {c}
            </blockquote>
          ),
          table: ({ children: c }) => (
            <div className={cn('my-3 overflow-x-auto rounded-lg border', border)}>
              <table className={cn('min-w-full text-xs', tableDivide)}>{c}</table>
            </div>
          ),
          thead: ({ children: c }) => <thead className={tableHeadBg}>{c}</thead>,
          th: ({ children: c }) => (
            <th
              className={cn(
                'px-3 py-2 text-left font-semibold border-b',
                thText,
                border,
              )}
            >
              {c}
            </th>
          ),
          td: ({ children: c }) => (
            <td className={cn('px-3 py-2 align-top border-b', tdText, tdBorder)}>{c}</td>
          ),
          tr: ({ children: c }) => <tr>{c}</tr>,
          code: ({ className: codeClassName, children: c }) => {
            const isBlock = Boolean(codeClassName)
            if (isBlock) {
              return (
                <code
                  className={cn(
                    'block overflow-x-auto rounded-lg p-3 text-xs font-mono my-2',
                    codeBg,
                    text,
                  )}
                >
                  {c}
                </code>
              )
            }
            return (
              <code className={cn('rounded px-1 py-0.5 text-xs font-mono', codeBg, text)}>
                {c}
              </code>
            )
          },
          pre: ({ children: c }) => <pre className="my-2">{c}</pre>,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
