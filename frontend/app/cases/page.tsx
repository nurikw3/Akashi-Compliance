import Link from 'next/link'
import { Plus } from 'lucide-react'
import { CasesList } from '@/components/cases-list'

export default function CasesPage() {
  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 mb-1">Контрагенты</h1>
          <p className="text-sm text-neutral-500">
            Сгруппированы по графу связей — связанные компании под главным узлом
          </p>
        </div>
        <Link
          href="/"
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          Добавить
        </Link>
      </div>
      <CasesList />
    </div>
  )
}
