'use client'

import * as React from 'react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { SourceInfo } from '@/lib/source-ref'
import { cn } from '@/lib/utils'

/**
 * Small inline chip that attributes a fact/block to its data source
 * (provider + endpoint). Renders nothing when no provider is known, so callers
 * can drop it next to any fact without conditionals.
 *
 *   <SourceRef provider="Adata" endpoint="/company/info" />
 *   <SourceRef source={resolveSectionSource(dataSources, log, 'courts')} />
 */
export function SourceRef({
  provider,
  endpoint,
  url,
  source,
  className,
}: {
  provider?: string
  endpoint?: string
  url?: string
  source?: SourceInfo
  className?: string
}) {
  const prov = source?.provider ?? provider
  const ep = source?.endpoint ?? endpoint
  const href = source?.url ?? url

  if (!prov || prov === '—') return null

  const chipClass = cn(
    'ml-1 inline-flex items-center rounded-sm border border-neutral-200 bg-neutral-50 px-1 text-[10px] font-medium leading-4 align-middle',
    href
      ? 'cursor-pointer text-blue-600 hover:bg-blue-50 hover:underline'
      : 'cursor-help text-neutral-500',
    className,
  )

  const tooltipText = (
    <>
      Источник: {prov}
      {ep ? ` · ${ep}` : ''}
      {href ? ` · ${href}` : ''}
    </>
  )

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer" className={chipClass}>
            {prov} ↗
          </a>
        ) : (
          <span className={chipClass}>{prov}</span>
        )}
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-pretty">{tooltipText}</TooltipContent>
    </Tooltip>
  )
}
