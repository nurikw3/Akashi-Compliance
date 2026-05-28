'use client'

import { useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Upload, FileSpreadsheet, FileText, X, Check, AlertCircle } from 'lucide-react'
import * as XLSX from 'xlsx'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { checkUploadDuplicates, type DuplicateMatch, parseImportFile } from '@/lib/api'
import { useCases } from '@/lib/cases-context'

interface ParsedRow {
  name: string
  iinBin: string
  extraData: Record<string, string>
  valid: boolean
  error?: string
}

export function ExcelUploader() {
  const [isDragging, setIsDragging] = useState(false)
  const [parsedData, setParsedData] = useState<ParsedRow[] | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [duplicateMatches, setDuplicateMatches] = useState<DuplicateMatch[] | null>(null)
  const { addCases, apiConnected } = useCases()
  const router = useRouter()

  const statusLabel: Record<string, string> = {
    ready: 'готово',
    pending: 'ожидание',
    enriching: 'проверка',
    error: 'ошибка',
  }

  const parseExcelFile = useCallback((file: File): Promise<ParsedRow[]> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()

      reader.onload = (e) => {
        try {
          const data = new Uint8Array(e.target?.result as ArrayBuffer)
          const workbook = XLSX.read(data, { type: 'array' })
          const firstSheet = workbook.Sheets[workbook.SheetNames[0]]
          const jsonData = XLSX.utils.sheet_to_json<Record<string, unknown>>(firstSheet)

          const parsed: ParsedRow[] = jsonData.map((row) => {
            const keys = Object.keys(row)

            const nameKey = keys.find(
              (k) =>
                k.toLowerCase().includes('name') ||
                k.toLowerCase().includes('название') ||
                k.toLowerCase().includes('наименование') ||
                k.toLowerCase().includes('компания')
            )

            const iinKey = keys.find(
              (k) =>
                k.toLowerCase().includes('iin') ||
                k.toLowerCase().includes('bin') ||
                k.toLowerCase().includes('иин') ||
                k.toLowerCase().includes('бин') ||
                k.toLowerCase().includes('рнн')
            )

            const name = nameKey ? String(row[nameKey] || '').trim() : ''
            const iinBin = iinKey ? String(row[iinKey] || '').replace(/\D/g, '') : ''

            const extraData: Record<string, string> = {}
            keys.forEach((k) => {
              if (k !== nameKey && k !== iinKey && row[k]) {
                extraData[k] = String(row[k])
              }
            })

            let valid = true
            let error: string | undefined

            if (!name) {
              valid = false
              error = 'Отсутствует название'
            } else if (!iinBin) {
              valid = false
              error = 'Отсутствует ИИН/БИН'
            } else if (iinBin.length !== 12) {
              valid = false
              error = 'ИИН/БИН должен содержать 12 цифр'
            }

            return { name, iinBin, extraData, valid, error }
          })

          resolve(parsed)
        } catch (error) {
          reject(error)
        }
      }

      reader.onerror = () => reject(reader.error)
      reader.readAsArrayBuffer(file)
    })
  }, [])

  const processFile = useCallback(
    async (file: File) => {
      setIsProcessing(true)
      try {
        const lowerName = file.name.toLowerCase()
        if (lowerName.endsWith('.docx')) {
          const rows = await parseImportFile(file)
          setParsedData(rows)
          return
        }

        const parsed = await parseExcelFile(file)
        setParsedData(parsed)
      } catch {
        alert(
          'Ошибка при чтении файла. Убедитесь, что это корректный Excel или Word (.docx) файл.'
        )
      } finally {
        setIsProcessing(false)
      }
    },
    [parseExcelFile]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)

      const file = e.dataTransfer.files[0]
      const lower = file?.name.toLowerCase() ?? ''
      if (file && (lower.endsWith('.xlsx') || lower.endsWith('.xls') || lower.endsWith('.docx'))) {
        void processFile(file)
      } else {
        alert('Пожалуйста, загрузите файл Excel (.xlsx, .xls) или Word (.docx)')
      }
    },
    [processFile]
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) processFile(file)
    },
    [processFile]
  )

  const runImport = useCallback(
    async (onDuplicate: 'skip' | 'refresh') => {
      if (!parsedData) return
      const validCases = parsedData.filter((r) => r.valid)
      setIsSubmitting(true)
      try {
        await addCases(validCases, { onDuplicate })
        setParsedData(null)
        setDuplicateMatches(null)
        router.push('/cases')
      } catch {
        alert('Не удалось импортировать. Проверьте, что backend запущен.')
      } finally {
        setIsSubmitting(false)
      }
    },
    [parsedData, addCases, router]
  )

  const handleSubmit = useCallback(async () => {
    if (!parsedData) return

    const validCases = parsedData.filter((r) => r.valid)
    if (validCases.length === 0) {
      alert('Нет валидных записей для импорта')
      return
    }

    if (!apiConnected) {
      await runImport('skip')
      return
    }

    setIsSubmitting(true)
    try {
      const { matches } = await checkUploadDuplicates(validCases.map((r) => r.iinBin))
      if (matches.length > 0) {
        setDuplicateMatches(matches)
        return
      }
      await runImport('skip')
    } catch {
      alert('Не удалось проверить дубликаты. Проверьте подключение к API.')
    } finally {
      setIsSubmitting(false)
    }
  }, [parsedData, apiConnected, runImport])

  const duplicateBins = new Set(duplicateMatches?.map((m) => m.iinBin) ?? [])

  const validCount = parsedData?.filter((r) => r.valid).length ?? 0
  const invalidCount = parsedData?.filter((r) => !r.valid).length ?? 0

  return (
    <div className="w-full max-w-2xl mx-auto">
      {!parsedData ? (
        <div
          className={`
            relative border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer
            ${isDragging ? 'border-blue-500 bg-blue-50' : 'border-neutral-300 hover:border-neutral-400 bg-white'}
          `}
          onDragOver={(e) => {
            e.preventDefault()
            setIsDragging(true)
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => document.getElementById('file-input')?.click()}
        >
          <input
            id="file-input"
            type="file"
            accept=".xlsx,.xls,.docx"
            className="hidden"
            onChange={handleFileSelect}
          />

          <div className="flex flex-col items-center gap-4">
            {isProcessing ? (
              <>
                <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
                <p className="text-neutral-600">Обработка файла...</p>
              </>
            ) : (
              <>
                <div className="w-16 h-16 rounded-full bg-blue-100 flex items-center justify-center">
                  <Upload className="w-8 h-8 text-blue-600" />
                </div>
                <div>
                  <p className="text-lg font-medium text-neutral-900">
                    Перетащите файл с контрагентами
                  </p>
                  <p className="text-sm text-neutral-500 mt-1">или нажмите для выбора файла</p>
                </div>
                <div className="flex items-center justify-center gap-4 text-xs text-neutral-400">
                  <span className="inline-flex items-center gap-1">
                    <FileSpreadsheet className="w-4 h-4" />
                    .xlsx, .xls
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <FileText className="w-4 h-4" />
                    .docx
                  </span>
                </div>
              </>
            )}
          </div>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-neutral-200 overflow-hidden">
          <div className="p-4 border-b border-neutral-200 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <FileSpreadsheet className="w-5 h-5 text-neutral-500" />
              <div>
                <p className="font-medium text-neutral-900">Предпросмотр данных</p>
                <p className="text-sm text-neutral-500">
                  {validCount} записей готово к импорту
                  {invalidCount > 0 && `, ${invalidCount} с ошибками`}
                </p>
              </div>
            </div>
            <button
              onClick={() => setParsedData(null)}
              className="p-2 hover:bg-neutral-100 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-neutral-500" />
            </button>
          </div>

          <div className="max-h-80 overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 sticky top-0">
                <tr>
                  <th className="text-left p-3 font-medium text-neutral-600">Статус</th>
                  <th className="text-left p-3 font-medium text-neutral-600">Название</th>
                  <th className="text-left p-3 font-medium text-neutral-600">ИИН/БИН</th>
                </tr>
              </thead>
              <tbody>
                {parsedData.map((row, i) => (
                  <tr key={i} className="border-t border-neutral-100">
                    <td className="p-3">
                      {row.valid ? (
                        <span className="inline-flex items-center gap-1 text-green-600">
                          <Check className="w-4 h-4" />
                          {duplicateBins.has(row.iinBin) && (
                            <span className="text-xs text-amber-600 font-normal">в базе</span>
                          )}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-red-500" title={row.error}>
                          <AlertCircle className="w-4 h-4" />
                        </span>
                      )}
                    </td>
                    <td className="p-3 text-neutral-900">{row.name || '—'}</td>
                    <td className="p-3 font-mono text-neutral-600">{row.iinBin || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="p-4 border-t border-neutral-200 flex justify-end gap-3">
            <button
              onClick={() => setParsedData(null)}
              className="px-4 py-2 text-neutral-600 hover:bg-neutral-100 rounded-lg transition-colors"
            >
              Отмена
            </button>
            <button
              onClick={() => void handleSubmit()}
              disabled={validCount === 0 || isSubmitting}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting
                ? 'Проверка…'
                : `Импортировать ${validCount} ${validCount === 1 ? 'запись' : 'записей'}`}
            </button>
          </div>
        </div>
      )}

      <AlertDialog
        open={duplicateMatches !== null && duplicateMatches.length > 0}
        onOpenChange={(open) => {
          if (!open) setDuplicateMatches(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Найдены дубликаты</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3 text-left text-neutral-600">
                <p>
                  {duplicateMatches?.length === 1
                    ? '1 контрагент уже есть в базе'
                    : `${duplicateMatches?.length} контрагентов уже есть в базе`}
                  . Новые записи по другим БИН будут добавлены как обычно.
                </p>
                <ul className="max-h-40 overflow-auto rounded-lg border border-neutral-200 divide-y divide-neutral-100 text-sm">
                  {duplicateMatches?.map((m) => (
                    <li key={m.iinBin} className="px-3 py-2">
                      <p className="font-medium text-neutral-900">{m.name}</p>
                      <p className="font-mono text-xs text-neutral-500">
                        {m.iinBin} · {statusLabel[m.status] ?? m.status}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="flex-col sm:flex-row gap-2">
            <AlertDialogCancel disabled={isSubmitting}>Отмена</AlertDialogCancel>
            <AlertDialogAction
              disabled={isSubmitting}
              className="bg-white text-neutral-900 border border-neutral-200 hover:bg-neutral-50"
              onClick={(e) => {
                e.preventDefault()
                void runImport('skip')
              }}
            >
              Оставить как есть
            </AlertDialogAction>
            <AlertDialogAction
              disabled={isSubmitting}
              className="bg-blue-600 hover:bg-blue-700"
              onClick={(e) => {
                e.preventDefault()
                void runImport('refresh')
              }}
            >
              Обновить из Adata
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <div className="mt-6 p-4 bg-neutral-50 rounded-lg">
        <p className="text-sm text-neutral-600 font-medium mb-2">Требования к файлу:</p>
        <ul className="text-sm text-neutral-500 space-y-1">
          <li>• Excel: колонки с названием и ИИН/БИН (гибкие заголовки)</li>
          <li>• Word (.docx): таблица или строки вида «Название — компания — 12 цифр БИН»</li>
          <li>• Дополнительные колонки Excel сохраняются в карточке</li>
        </ul>
      </div>
    </div>
  )
}
