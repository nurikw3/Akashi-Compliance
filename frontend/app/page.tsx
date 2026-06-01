import { BinUploader } from '@/components/bin-uploader'
import { ExcelUploader } from '@/components/excel-uploader'

export default function HomePage() {
  return (
    <div className="space-y-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-neutral-900 mb-2">
          Загрузка контрагентов
        </h1>
        <p className="text-neutral-500">
          БИН слева, Excel / Word справа — проверка через Adata API
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
        <section aria-labelledby="bin-upload-heading" className="flex flex-col min-h-0">
          <h2
            id="bin-upload-heading"
            className="text-base font-semibold text-neutral-900 mb-3"
          >
            Ввод БИН / ИИН
          </h2>
          <BinUploader className="flex-1 min-h-0" />
        </section>

        <section aria-labelledby="file-upload-heading" className="flex flex-col min-h-0">
          <h2
            id="file-upload-heading"
            className="text-base font-semibold text-neutral-900 mb-3"
          >
            Файл Excel / Word
          </h2>
          <ExcelUploader className="flex-1 min-h-0" />
        </section>
      </div>
    </div>
  )
}
