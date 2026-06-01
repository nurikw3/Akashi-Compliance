'use client'

import { useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Upload, X, Check, AlertCircle, Hash } from 'lucide-react'
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
import {
  checkUploadDuplicates,
  parseBinsLocally,
  parseBinsText,
  parseImportFile,
  type DuplicateMatch,
  type ImportPreviewRow,
} from '@/lib/api'
import { useCases } from '@/lib/cases-context'
import { cn } from '@/lib/utils'

type BinUploaderProps = {
  className?: string
}

export function BinUploader({ className }: BinUploaderProps) {
  const [binText, setBinText] = useState('')
  const [parsedData, setParsedData] = useState<ImportPreviewRow[] | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [parseError, setParseError] = useState<string | null>(null)
  const [duplicateMatches, setDuplicateMatches] = useState<DuplicateMatch[] | null>(null)
  const { addCases, apiConnected } = useCases()
  const router = useRouter()

  const statusLabel: Record<string, string> = {
    ready: 'готово',
    pending: 'ожидание',
    enriching: 'проверка',
    error: 'ошибка',
  }

  const applyParsed = useCallback((rows: ImportPreviewRow[]) => {
    if (rows.length === 0) {
      setParseError('Не найдено ни одного 12-значного БИН/ИИН')
      setParsedData(null)
      return
    }
    setParseError(null)
    setParsedData(rows)
  }, [])

  const parseFromText = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed) {
        setParseError('Введите или вставьте список БИН')
        return
      }
      setIsProcessing(true)
      try {
        if (apiConnected) {
          const rows = await parseBinsText(trimmed)
          applyParsed(rows)
        } else {
          applyParsed(parseBinsLocally(trimmed))
        }
      } catch {
        applyParsed(parseBinsLocally(trimmed))
      } finally {
        setIsProcessing(false)
      }
    },
    [apiConnected, applyParsed]
  )

  const processTxtFile = useCallback(
    async (file: File) => {
      setIsProcessing(true)
      try {
        if (apiConnected) {
          const rows = await parseImportFile(file)
          applyParsed(rows.filter((r) => r.valid))
          return
        }
        const text = await file.text()
        setBinText(text)
        applyParsed(parseBinsLocally(text))
      } catch {
        setParseError('Не удалось прочитать файл')
      } finally {
        setIsProcessing(false)
      }
    },
    [apiConnected, applyParsed]
  )

  const handleTxtSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return
      const lower = file.name.toLowerCase()
      if (!lower.endsWith('.txt') && !lower.endsWith('.csv')) {
        alert('Для списка БИН используйте .txt или .csv')
        return
      }
      void processTxtFile(file)
      e.target.value = ''
    },
    [processTxtFile]
  )

  const runImport = useCallback(
    async (onDuplicate: 'skip' | 'refresh') => {
      if (!parsedData) return
      const validCases = parsedData.filter((r) => r.valid)
      setIsSubmitting(true)
      try {
        await addCases(validCases, { onDuplicate })
        setParsedData(null)
        setBinText('')
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

  if (parsedData) {
    return (
      <div className={cn('w-full', className)}>
        <div className="bg-white rounded-xl border border-neutral-200 overflow-hidden">
          <div className="p-4 border-b border-neutral-200 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Hash className="w-5 h-5 text-neutral-500" />
              <div>
                <p className="font-medium text-neutral-900">Список БИН</p>
                <p className="text-sm text-neutral-500">
                  {validCount} записей готово к импорту
                  {invalidCount > 0 && `, ${invalidCount} с ошибками`}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setParsedData(null)}
              className="p-2 hover:bg-neutral-100 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-neutral-500" />
            </button>
          </div>

          <div className="max-h-52 overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 sticky top-0">
                <tr>
                  <th className="text-left p-3 font-medium text-neutral-600">Статус</th>
                  <th className="text-left p-3 font-medium text-neutral-600">ИИН/БИН</th>
                  <th className="text-left p-3 font-medium text-neutral-600 hidden sm:table-cell">
                    Название
                  </th>
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
                        <span
                          className="inline-flex items-center gap-1 text-red-500"
                          title={row.error}
                        >
                          <AlertCircle className="w-4 h-4" />
                        </span>
                      )}
                    </td>
                    <td className="p-3 font-mono text-neutral-900">{row.iinBin || '—'}</td>
                    <td className="p-3 text-neutral-500 hidden sm:table-cell">{row.name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="p-4 border-t border-neutral-200 flex justify-end gap-3">
            <button
              type="button"
              onClick={() => setParsedData(null)}
              className="px-4 py-2 text-neutral-600 hover:bg-neutral-100 rounded-lg transition-colors"
            >
              Назад
            </button>
            <button
              type="button"
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
                      ? '1 БИН уже есть в базе'
                      : `${duplicateMatches?.length} БИН уже есть в базе`}
                    . Остальные будут добавлены как обычно.
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
      </div>
    )
  }

  return (
    <div className={cn('w-full flex flex-col', className)}>
      <div className="flex flex-col flex-1 rounded-xl border-2 border-blue-200 bg-white p-4 shadow-sm min-h-[280px]">
        <label htmlFor="bin-text" className="block text-sm font-semibold text-neutral-900 mb-1">
          Вставьте БИН (12 цифр)
        </label>
        <p className="text-xs text-neutral-500 mb-2">
          По строке, через запятую или пробел. Название — из Adata.
        </p>
        <textarea
          id="bin-text"
          name="bin-list"
          autoFocus
          value={binText}
          onChange={(e) => {
            setBinText(e.target.value)
            setParseError(null)
          }}
          placeholder={'191040900016\n171040021791'}
          className="flex-1 min-h-[140px] w-full rounded-lg border border-neutral-300 px-3 py-2 font-mono text-sm text-neutral-900 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
        />
        {parseError && <p className="mt-2 text-sm text-red-600">{parseError}</p>}
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void parseFromText(binText)}
            disabled={isProcessing || !binText.trim()}
            className="px-3 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isProcessing ? 'Разбор…' : 'Разобрать список'}
          </button>
          <label className="inline-flex items-center gap-2 px-3 py-2 text-sm border border-neutral-200 rounded-lg text-neutral-700 hover:bg-neutral-50 cursor-pointer transition-colors">
            <Upload className="w-4 h-4" />
            .txt / .csv
            <input
              type="file"
              accept=".txt,.csv"
              className="hidden"
              onChange={handleTxtSelect}
            />
          </label>
        </div>
      </div>
    </div>
  )
}
