import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import { CaseDetail } from '@/components/case-detail'

export default async function CaseDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params

  return (
    <div>
      <Link
        href="/cases"
        className="inline-flex items-center gap-2 text-neutral-500 hover:text-neutral-700 mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Назад к списку
      </Link>
      <CaseDetail caseId={id} />
    </div>
  )
}
