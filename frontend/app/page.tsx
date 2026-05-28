import { ExcelUploader } from '@/components/excel-uploader'

export default function HomePage() {
  return (
    <div>
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-neutral-900 mb-3">
          Загрузка контрагентов
        </h1>
        <p className="text-neutral-500 max-w-lg mx-auto">
          Загрузите Excel файл со списком компаний для автоматической проверки через Adata API
        </p>
      </div>
      <ExcelUploader />
    </div>
  )
}
