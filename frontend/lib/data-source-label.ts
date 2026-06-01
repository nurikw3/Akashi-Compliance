import type { DataSourceKind, DataSources } from '@/lib/types'

export function dataSourceLabel(kind?: DataSourceKind): string {
  if (kind === 'adata') return '(Adata)'
  return '(нет данных)'
}

export function sectionSource(
  dataSources: DataSources | undefined,
  section: keyof DataSources
): DataSourceKind {
  if (!dataSources) return 'none'
  const kind = dataSources[section] ?? 'none'
  return kind === 'stub' ? 'none' : kind
}
