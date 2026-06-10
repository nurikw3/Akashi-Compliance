'use client'

import * as React from 'react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { defineTerm } from '@/lib/abbreviations'
import { cn } from '@/lib/utils'

/**
 * Wraps an abbreviation/term and shows its full definition from the glossary
 * on hover. If the term is unknown, renders the text unchanged (no tooltip).
 *
 *   <Abbr code="PEP" />            → renders "PEP" with a tooltip
 *   <Abbr code="БИН">{value}</Abbr> → custom visible text, "БИН" definition
 */
export function Abbr({
  code,
  children,
  className,
}: {
  code: string
  children?: React.ReactNode
  className?: string
}) {
  const definition = defineTerm(code)
  const label = children ?? code

  if (!definition) {
    return <>{label}</>
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <abbr
          title={undefined}
          className={cn(
            'cursor-help no-underline decoration-dotted underline-offset-2 [text-decoration-line:underline]',
            className,
          )}
        >
          {label}
        </abbr>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-pretty">{definition}</TooltipContent>
    </Tooltip>
  )
}
