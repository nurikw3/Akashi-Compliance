import Link from 'next/link'
import { Plus } from 'lucide-react'
import { CasesList } from '@/components/cases-list'

export default function CasesPage() {
  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-neutral-900 mb-2">Дела</h1>
          <p className="text-neutral-500">
            Контрагенты сгруппированы по графу связей — связанные компании под главным узлом
          </p>
        </div>
        <Link
          href="/"
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Загрузить файл
        </Link>
      </div>
      <CasesList />
    </div>
  )
}
