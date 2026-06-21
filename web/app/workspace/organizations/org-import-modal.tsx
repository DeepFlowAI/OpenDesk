'use client'

import { useCallback, useMemo, useRef, useState } from 'react'
import { IconDownload, IconUpload, IconX } from '@tabler/icons-react'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import type { Locale } from '@/context/locale-store'
import {
  downloadOrganizationImportErrorReport,
  downloadOrganizationImportTemplate,
  executeOrganizationImport,
  previewOrganizationImport,
} from '@/service/use-organizations'
import type {
  OrgImportPreviewResponse,
  OrgImportRowError,
} from '@/models/org-import'

type ImportStep = 'upload' | 'preview' | 'result'

type OrgImportModalProps = {
  locale: Locale
  open: boolean
  onClose: () => void
  onCompleted: () => void
}

const ACCEPTED_EXTENSIONS = ['.xlsx', '.csv']
const MAX_FILE_SIZE = 10 * 1024 * 1024

function triggerDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename || 'download.xlsx'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.URL.revokeObjectURL(url)
}

function reasonLabel(reason: string, locale: Locale): string {
  const keyMap: Record<string, string> = {
    'Organization name is required': 'ws.orgs.import.reason.nameRequired',
    'Organization name already exists': 'ws.orgs.import.reason.nameExists',
    'Duplicate organization name in file': 'ws.orgs.import.reason.duplicateNameInFile',
    'Invalid option value': 'ws.orgs.import.reason.invalidOption',
    'Invalid date format': 'ws.orgs.import.reason.invalidDate',
    'Invalid datetime format': 'ws.orgs.import.reason.invalidDatetime',
    'Invalid number format': 'ws.orgs.import.reason.invalidNumber',
    'Unsupported columns detected': 'ws.orgs.import.reason.unsupportedColumns',
    'Import failed': 'ws.orgs.import.reason.importFailed',
  }
  const key = keyMap[reason]
  return key ? t(key, locale) : reason
}

export function OrgImportModal({ locale, open, onClose, onCompleted }: OrgImportModalProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [step, setStep] = useState<ImportStep>('upload')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<OrgImportPreviewResponse | null>(null)
  const [allErrors, setAllErrors] = useState<OrgImportRowError[]>([])
  const [fileHeaders, setFileHeaders] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [resultSummary, setResultSummary] = useState<{
    created: number
    failed: number
    skipped: number
    total: number
  } | null>(null)
  const [resultErrors, setResultErrors] = useState<OrgImportRowError[]>([])

  const isBusy = loading
  const canConfirmImport = (preview?.summary.importable_rows ?? 0) > 0

  const resetState = useCallback(() => {
    setStep('upload')
    setSelectedFile(null)
    setPreview(null)
    setAllErrors([])
    setFileHeaders([])
    setResultSummary(null)
    setResultErrors([])
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [])

  const handleClose = useCallback(() => {
    if (isBusy) return
    if (step === 'preview' && preview) {
      const confirmed = window.confirm(t('ws.orgs.import.exitConfirm', locale))
      if (!confirmed) return
    }
    resetState()
    onClose()
  }, [isBusy, locale, onClose, preview, resetState, step])

  const validateFile = useCallback((file: File): string | null => {
    const lowerName = file.name.toLowerCase()
    if (!ACCEPTED_EXTENSIONS.some((ext) => lowerName.endsWith(ext))) {
      return t('ws.orgs.import.error.unsupportedFormat', locale)
    }
    if (file.size > MAX_FILE_SIZE) {
      return t('ws.orgs.import.error.fileTooLarge', locale)
    }
    return null
  }, [locale])

  const handlePickFile = useCallback((file: File | null) => {
    if (!file) {
      setSelectedFile(null)
      setPreview(null)
      setAllErrors([])
      setFileHeaders([])
      return
    }
    const error = validateFile(file)
    if (error) {
      toast.error(error)
      return
    }
    setSelectedFile(file)
    setPreview(null)
    setAllErrors([])
    setFileHeaders([])
    setStep('upload')
  }, [validateFile])

  const handleDownloadTemplate = useCallback(async () => {
    setLoading(true)
    try {
      const result = await downloadOrganizationImportTemplate(locale)
      triggerDownload(result.blob, result.filename)
    } catch {
      toast.error(t('ws.orgs.import.error.templateFailed', locale))
    } finally {
      setLoading(false)
    }
  }, [locale])

  const handlePreview = useCallback(async () => {
    if (!selectedFile || isBusy) return
    setLoading(true)
    try {
      const response = await previewOrganizationImport(selectedFile, locale)
      setPreview(response)
      setAllErrors(response.errors)
      setFileHeaders(response.file_headers)
      setStep('preview')
      toast.success(t('ws.orgs.import.previewDone', locale))
    } catch {
      toast.error(t('ws.orgs.import.error.previewFailed', locale))
    } finally {
      setLoading(false)
    }
  }, [isBusy, locale, selectedFile])

  const handleExecute = useCallback(async () => {
    if (!preview || !canConfirmImport || isBusy) return
    setLoading(true)
    try {
      const response = await executeOrganizationImport(preview.preview_token)
      setResultSummary({
        created: response.summary.created,
        failed: response.summary.failed,
        skipped: response.summary.skipped,
        total: response.summary.total_rows,
      })
      setResultErrors(response.errors)
      setStep('result')
      if (response.summary.created > 0 && response.summary.failed === 0) {
        toast.success(t('ws.orgs.import.success.all', locale))
      } else if (response.summary.created > 0) {
        toast.warning(t('ws.orgs.import.success.partial', locale))
      } else {
        toast.error(t('ws.orgs.import.success.failed', locale))
      }
    } catch {
      toast.error(t('ws.orgs.import.error.executeFailed', locale))
    } finally {
      setLoading(false)
    }
  }, [canConfirmImport, isBusy, locale, preview])

  const errorRowsForReport = useMemo(() => {
    const source = step === 'result' ? resultErrors : allErrors
    return source.map((item) => ({
      row_number: item.row_number,
      values: item.raw_values,
      error_reason: reasonLabel(item.reason, locale),
    }))
  }, [allErrors, locale, resultErrors, step])

  const handleDownloadErrorReport = useCallback(async () => {
    if (errorRowsForReport.length === 0) return
    setLoading(true)
    try {
      const headers = fileHeaders.length > 0
        ? fileHeaders
        : preview?.column_mappings.map((item) => item.file_header) ?? []
      const result = await downloadOrganizationImportErrorReport(
        { headers, rows: errorRowsForReport },
        locale,
      )
      triggerDownload(result.blob, result.filename)
    } catch {
      toast.error(t('ws.orgs.import.error.reportFailed', locale))
    } finally {
      setLoading(false)
    }
  }, [errorRowsForReport, fileHeaders, locale, preview?.column_mappings])

  const handleFinish = useCallback(() => {
    resetState()
    onCompleted()
    onClose()
  }, [onClose, onCompleted, resetState])

  const handleContinueImport = useCallback(() => {
    resetState()
  }, [resetState])

  const stepTitle = step === 'upload'
    ? t('ws.orgs.import.step.upload', locale)
    : step === 'preview'
      ? t('ws.orgs.import.step.preview', locale)
      : t('ws.orgs.import.step.result', locale)

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && handleClose()}>
      <DialogContent className="flex max-h-[85vh] max-w-[760px] flex-col gap-0 p-0">
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle>{t('ws.orgs.import.title', locale)}</DialogTitle>
          <DialogDescription>{stepTitle}</DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {step === 'upload' && (
            <UploadStep
              locale={locale}
              selectedFile={selectedFile}
              loading={loading}
              fileInputRef={fileInputRef}
              onPickFile={handlePickFile}
              onDownloadTemplate={handleDownloadTemplate}
            />
          )}

          {step === 'preview' && preview && (
            <PreviewStep
              locale={locale}
              preview={preview}
              onDownloadErrorReport={handleDownloadErrorReport}
            />
          )}

          {step === 'result' && resultSummary && (
            <ResultStep locale={locale} summary={resultSummary} />
          )}
        </div>

        <DialogFooter className="border-t px-6 py-4">
          {step === 'upload' && (
            <>
              <Button type="button" variant="outline" onClick={handleClose} disabled={isBusy}>
                {t('ws.orgs.import.action.cancel', locale)}
              </Button>
              <Button type="button" onClick={handlePreview} disabled={!selectedFile || isBusy}>
                {isBusy ? t('ws.orgs.import.action.processing', locale) : t('ws.orgs.import.action.next', locale)}
              </Button>
            </>
          )}

          {step === 'preview' && (
            <>
              <Button type="button" variant="outline" onClick={() => setStep('upload')} disabled={isBusy}>
                {t('ws.orgs.import.action.back', locale)}
              </Button>
              {allErrors.length > 0 && (
                <Button type="button" variant="outline" onClick={handleDownloadErrorReport} disabled={isBusy}>
                  {t('ws.orgs.import.action.downloadErrors', locale)}
                </Button>
              )}
              <Button type="button" onClick={handleExecute} disabled={!canConfirmImport || isBusy}>
                {isBusy ? t('ws.orgs.import.action.importing', locale) : t('ws.orgs.import.action.confirm', locale)}
              </Button>
            </>
          )}

          {step === 'result' && (
            <>
              {(resultErrors.length > 0 || (resultSummary?.skipped ?? 0) > 0) && (
                <Button type="button" variant="outline" onClick={handleDownloadErrorReport} disabled={isBusy}>
                  {t('ws.orgs.import.action.downloadErrors', locale)}
                </Button>
              )}
              <Button type="button" variant="outline" onClick={handleContinueImport} disabled={isBusy}>
                {t('ws.orgs.import.action.continue', locale)}
              </Button>
              <Button type="button" onClick={handleFinish} disabled={isBusy}>
                {t('ws.orgs.import.action.finish', locale)}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function UploadStep({
  locale,
  selectedFile,
  loading,
  fileInputRef,
  onPickFile,
  onDownloadTemplate,
}: {
  locale: Locale
  selectedFile: File | null
  loading: boolean
  fileInputRef: React.RefObject<HTMLInputElement | null>
  onPickFile: (file: File | null) => void
  onDownloadTemplate: () => void
}) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-muted/20 p-4 text-sm text-muted-foreground">
        <p>{t('ws.orgs.import.uploadHint', locale)}</p>
        <button
          type="button"
          onClick={onDownloadTemplate}
          disabled={loading}
          className="mt-3 inline-flex items-center gap-1.5 text-primary hover:underline"
        >
          <IconDownload size={16} />
          {t('ws.orgs.import.downloadTemplate', locale)}
        </button>
      </div>

      <label
        className={cn(
          'flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-border px-6 py-10 text-center transition-colors hover:bg-accent/40',
          loading && 'pointer-events-none opacity-60',
        )}
      >
        <IconUpload size={28} className="mb-3 text-muted-foreground" />
        <p className="text-sm font-medium text-foreground">
          {t('ws.orgs.import.dropHint', locale)}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {t('ws.orgs.import.fileRules', locale)}
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx,.csv"
          className="hidden"
          onChange={(event) => onPickFile(event.target.files?.[0] ?? null)}
        />
      </label>

      {selectedFile && (
        <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-sm">
          <div className="min-w-0">
            <p className="truncate font-medium text-foreground">{selectedFile.name}</p>
            <p className="text-xs text-muted-foreground">
              {(selectedFile.size / 1024).toFixed(1)} KB
            </p>
          </div>
          <button
            type="button"
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            onClick={() => {
              if (fileInputRef.current) fileInputRef.current.value = ''
              onPickFile(null)
            }}
          >
            <IconX size={16} />
          </button>
        </div>
      )}
    </div>
  )
}

function PreviewStep({
  locale,
  preview,
  onDownloadErrorReport,
}: {
  locale: Locale
  preview: OrgImportPreviewResponse
  onDownloadErrorReport: () => void
}) {
  return (
    <div className="space-y-5">
      <div className="grid gap-3 rounded-lg border border-border bg-muted/20 p-4 text-sm sm:grid-cols-2">
        <SummaryItem label={t('ws.orgs.import.summary.filename', locale)} value={preview.summary.filename} />
        <SummaryItem label={t('ws.orgs.import.summary.total', locale)} value={String(preview.summary.total_rows)} />
        <SummaryItem label={t('ws.orgs.import.summary.importable', locale)} value={String(preview.summary.importable_rows)} />
        <SummaryItem label={t('ws.orgs.import.summary.blocked', locale)} value={String(preview.summary.blocked_rows)} />
      </div>

      {preview.summary.importable_rows > 0 && preview.errors.length > 0 && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-100">
          {t('ws.orgs.import.partialImportHint', locale)}
        </p>
      )}

      <section>
        <h4 className="mb-2 text-sm font-semibold">{t('ws.orgs.import.columnsTitle', locale)}</h4>
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">{t('ws.orgs.import.columns.fileHeader', locale)}</th>
                <th className="px-3 py-2 font-medium">{t('ws.orgs.import.columns.mapped', locale)}</th>
                <th className="px-3 py-2 font-medium">{t('ws.orgs.import.columns.status', locale)}</th>
              </tr>
            </thead>
            <tbody>
              {preview.column_mappings.map((column) => (
                <tr key={column.file_header} className="border-t border-border">
                  <td className="px-3 py-2">{column.file_header}</td>
                  <td className="px-3 py-2">{column.field_name ?? '—'}</td>
                  <td className="px-3 py-2">
                    {column.status === 'mapped'
                      ? t('ws.orgs.import.status.mapped', locale)
                      : t('ws.orgs.import.status.unsupported', locale)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {preview.errors.length > 0 && (
        <section>
          <div className="mb-2 flex items-center justify-between gap-3">
            <h4 className="text-sm font-semibold">{t('ws.orgs.import.errorsTitle', locale)}</h4>
            <button
              type="button"
              className="text-sm text-primary hover:underline"
              onClick={onDownloadErrorReport}
            >
              {t('ws.orgs.import.action.downloadErrors', locale)}
            </button>
          </div>
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-left text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">{t('ws.orgs.import.errors.row', locale)}</th>
                  <th className="px-3 py-2 font-medium">{t('ws.orgs.import.errors.identifier', locale)}</th>
                  <th className="px-3 py-2 font-medium">{t('ws.orgs.import.errors.field', locale)}</th>
                  <th className="px-3 py-2 font-medium">{t('ws.orgs.import.errors.reason', locale)}</th>
                </tr>
              </thead>
              <tbody>
                {preview.errors.map((error, index) => (
                  <tr key={`${error.row_number}-${index}`} className="border-t border-border">
                    <td className="px-3 py-2">{error.row_number}</td>
                    <td className="px-3 py-2">{error.identifier ?? '—'}</td>
                    <td className="px-3 py-2">{error.field}</td>
                    <td className="px-3 py-2">{reasonLabel(error.reason, locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {preview.has_more_errors && (
            <p className="mt-2 text-xs text-muted-foreground">
              {t('ws.orgs.import.errors.more', locale)}
            </p>
          )}
        </section>
      )}
    </div>
  )
}

function ResultStep({
  locale,
  summary,
}: {
  locale: Locale
  summary: { created: number; failed: number; skipped: number; total: number }
}) {
  const allSuccess = summary.created > 0 && summary.failed === 0
  const partial = summary.created > 0 && (summary.failed > 0 || summary.skipped > 0)
  const tone = allSuccess ? 'success' : partial ? 'warning' : 'error'
  const message = allSuccess
    ? t('ws.orgs.import.success.all', locale)
    : partial
      ? t('ws.orgs.import.success.partial', locale)
      : t('ws.orgs.import.success.failed', locale)

  return (
    <div className="space-y-4">
      <div
        className={cn(
          'rounded-lg border px-4 py-3 text-sm',
          tone === 'success' && 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-100',
          tone === 'warning' && 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-100',
          tone === 'error' && 'border-red-200 bg-red-50 text-red-900 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-100',
        )}
      >
        {message}
      </div>
      <div className="grid gap-3 rounded-lg border border-border bg-muted/20 p-4 text-sm sm:grid-cols-2">
        <SummaryItem label={t('ws.orgs.import.result.created', locale)} value={String(summary.created)} />
        <SummaryItem label={t('ws.orgs.import.result.failed', locale)} value={String(summary.failed)} />
        <SummaryItem label={t('ws.orgs.import.result.skipped', locale)} value={String(summary.skipped)} />
        <SummaryItem label={t('ws.orgs.import.result.total', locale)} value={String(summary.total)} />
      </div>
      <p className="text-xs text-muted-foreground">
        {t('ws.orgs.import.refreshHint', locale)}
      </p>
    </div>
  )
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-muted-foreground">{label}</p>
      <p className="mt-1 font-medium text-foreground">{value}</p>
    </div>
  )
}
