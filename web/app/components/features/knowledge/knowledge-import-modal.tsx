'use client'

import { useCallback, useMemo, useRef, useState, type RefObject } from 'react'
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
import type { Locale } from '@/context/locale-store'
import type {
  KnowledgeImportAction,
  KnowledgeImportPreviewResponse,
  KnowledgeImportRowResult,
  KnowledgeImportSummary,
} from '@/models/knowledge'
import {
  downloadKnowledgeImportTemplate,
  previewKnowledgeImport,
  useExecuteKnowledgeImport,
} from '@/service/use-knowledge'

type RowFilter = 'all' | KnowledgeImportAction

type KnowledgeImportModalProps = {
  locale: Locale
  open: boolean
  onClose: () => void
  onCompleted: () => void
}

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

function text(locale: Locale, zh: string, en: string): string {
  return locale === 'zh' ? zh : en
}

function actionLabel(action: KnowledgeImportAction, locale: Locale): string {
  const labels: Record<KnowledgeImportAction, [string, string]> = {
    create: ['新建', 'Create'],
    update: ['更新', 'Update'],
    skip: ['跳过', 'Skip'],
    error: ['错误', 'Error'],
  }
  const [zh, en] = labels[action]
  return text(locale, zh, en)
}

function errorLabel(reason: string, locale: Locale): string {
  if (locale !== 'zh') return reason
  if (reason.startsWith('Duplicate id with row')) return reason.replace('Duplicate id with row', '与第') + ' 行重复 id'
  if (reason.startsWith('Duplicate target with row')) return reason.replace('Duplicate target with row', '与第') + ' 行指向同一目标'
  const map: Record<string, string> = {
    'Invalid id': 'id 格式无效',
    'Document id does not exist in current tenant': 'id 不存在或不属于当前租户',
    'Directory path is required': '目录路径不能为空',
    'Directory path supports up to 3 levels': '目录最多支持 3 级',
    'Directory name cannot exceed 50 characters': '目录名称不能超过 50 个字符',
    'Title is required': '文档标题不能为空',
    'Title cannot exceed 120 characters': '文档标题不能超过 120 个字符',
    'Invalid status': '发布状态无效',
    'Invalid validity type': '有效期类型无效',
    'Invalid datetime format': '时间格式无效',
    'Valid period is required': '时限有效期需要开始和结束时间',
    'Valid end must be later than valid start': '结束时间必须晚于开始时间',
    'Content is required': '正文不能为空',
    'Document title already exists in target directory': '目标目录下已存在同名文档',
  }
  return map[reason] ?? reason
}

export function KnowledgeImportModal({ locale, open, onClose, onCompleted }: KnowledgeImportModalProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<KnowledgeImportPreviewResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [rowFilter, setRowFilter] = useState<RowFilter>('all')
  const [rowSearch, setRowSearch] = useState('')
  const executeImport = useExecuteKnowledgeImport()
  const busy = loading || executeImport.isPending
  const canConfirm = !!preview && !preview.has_errors && (preview.summary.create_documents + preview.summary.update_documents) > 0

  const resetState = useCallback(() => {
    setSelectedFile(null)
    setPreview(null)
    setLoading(false)
    setRowFilter('all')
    setRowSearch('')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [])

  const handleClose = useCallback(() => {
    if (busy) return
    if (preview) {
      const confirmed = window.confirm(text(locale, '关闭后将丢弃本次预检结果。', 'Closing will discard this preview.'))
      if (!confirmed) return
    }
    resetState()
    onClose()
  }, [busy, locale, onClose, preview, resetState])

  const validateFile = useCallback((file: File): string | null => {
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      return text(locale, '仅支持上传 .xlsx 文件', 'Only .xlsx files are supported')
    }
    if (file.size > MAX_FILE_SIZE) {
      return text(locale, '文件不能超过 10 MB', 'File size must be no more than 10 MB')
    }
    return null
  }, [locale])

  const handlePickFile = useCallback((file: File | null) => {
    if (!file) {
      setSelectedFile(null)
      return
    }
    const error = validateFile(file)
    if (error) {
      toast.error(error)
      return
    }
    setSelectedFile(file)
    setPreview(null)
  }, [validateFile])

  const handleDownloadTemplate = useCallback(async () => {
    setLoading(true)
    try {
      const result = await downloadKnowledgeImportTemplate(locale)
      triggerDownload(result.blob, result.filename)
      toast.success(text(locale, '已下载知识库导入模板', 'Knowledge import template downloaded'))
    } catch {
      toast.error(text(locale, '模板下载失败', 'Failed to download template'))
    } finally {
      setLoading(false)
    }
  }, [locale])

  const handlePreview = useCallback(async () => {
    if (!selectedFile || busy) return
    setLoading(true)
    try {
      const response = await previewKnowledgeImport(selectedFile, locale)
      setPreview(response)
      setRowFilter('all')
      setRowSearch('')
      toast.success(text(locale, 'Excel 检查完成', 'Excel validation completed'))
    } catch {
      toast.error(text(locale, '预检失败，请检查文件内容', 'Validation failed. Check the file and try again.'))
    } finally {
      setLoading(false)
    }
  }, [busy, locale, selectedFile])

  const handleExecute = useCallback(async () => {
    if (!preview || !canConfirm || busy) return
    try {
      const response = await executeImport.mutateAsync(preview.preview_token)
      if (response.has_errors) {
        setPreview({
          ...preview,
          summary: response.summary,
          rows: response.rows,
          has_errors: true,
        })
        toast.error(text(locale, '请修正错误后重新上传', 'Fix the errors and upload again'))
        return
      }
      toast.success(text(locale, '已导入知识库', 'Knowledge base imported'))
      resetState()
      onCompleted()
      onClose()
    } catch {
      toast.error(text(locale, '导入失败', 'Import failed'))
    }
  }, [busy, canConfirm, executeImport, locale, onClose, onCompleted, preview, resetState])

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && handleClose()}>
      <DialogContent className="flex max-h-[85vh] max-w-[820px] flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle>{text(locale, '导入知识库', 'Import Knowledge Base')}</DialogTitle>
          <DialogDescription>
            {preview
              ? text(locale, '预检结果', 'Validation results')
              : text(locale, '上传文件并预检后再确认导入', 'Upload and validate the file before importing')}
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {!preview ? (
            <UploadStep
              locale={locale}
              loading={busy}
              selectedFile={selectedFile}
              fileInputRef={fileInputRef}
              onPickFile={handlePickFile}
              onDownloadTemplate={handleDownloadTemplate}
            />
          ) : (
            <PreviewStep
              locale={locale}
              preview={preview}
              rowFilter={rowFilter}
              rowSearch={rowSearch}
              onFilterChange={setRowFilter}
              onSearchChange={setRowSearch}
            />
          )}
        </div>

        <DialogFooter className="border-t px-6 py-4">
          {!preview ? (
            <>
              <Button type="button" variant="outline" onClick={handleClose} disabled={busy}>
                {text(locale, '取消', 'Cancel')}
              </Button>
              <Button type="button" onClick={handlePreview} disabled={!selectedFile || busy}>
                {busy ? text(locale, '检查中...', 'Validating...') : text(locale, '预检', 'Validate')}
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="outline" onClick={resetState} disabled={busy}>
                {text(locale, '重新上传', 'Upload Again')}
              </Button>
              <Button type="button" onClick={handleExecute} disabled={!canConfirm || busy}>
                {busy ? text(locale, '导入中...', 'Importing...') : text(locale, '确认导入', 'Confirm Import')}
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
  loading,
  selectedFile,
  fileInputRef,
  onPickFile,
  onDownloadTemplate,
}: {
  locale: Locale
  loading: boolean
  selectedFile: File | null
  fileInputRef: RefObject<HTMLInputElement | null>
  onPickFile: (file: File | null) => void
  onDownloadTemplate: () => void
}) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-muted/20 p-4 text-sm text-muted-foreground">
        <p>{text(locale, '支持 .xlsx，最大 10 MB。导入前会先预检，不会立即写入。', 'Supports .xlsx up to 10 MB. The file is validated before any data is written.')}</p>
        <button
          type="button"
          onClick={onDownloadTemplate}
          disabled={loading}
          className="mt-3 inline-flex items-center gap-1.5 text-primary hover:underline"
        >
          <IconDownload size={16} />
          {text(locale, '下载 Excel 模板', 'Download Excel Template')}
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
          {text(locale, '选择或拖拽 Excel 文件', 'Choose or drop an Excel file')}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">Excel .xlsx</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx"
          className="hidden"
          onChange={(event) => onPickFile(event.target.files?.[0] ?? null)}
        />
      </label>

      {selectedFile && (
        <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-sm">
          <div className="min-w-0">
            <p className="truncate font-medium text-foreground">{selectedFile.name}</p>
            <p className="text-xs text-muted-foreground">{(selectedFile.size / 1024).toFixed(1)} KB</p>
          </div>
          <button
            type="button"
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            onClick={() => onPickFile(null)}
            title={text(locale, '移除文件', 'Remove file')}
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
  rowFilter,
  rowSearch,
  onFilterChange,
  onSearchChange,
}: {
  locale: Locale
  preview: KnowledgeImportPreviewResponse
  rowFilter: RowFilter
  rowSearch: string
  onFilterChange: (value: RowFilter) => void
  onSearchChange: (value: string) => void
}) {
  const rows = useMemo(() => filterRows(preview.rows, rowFilter, rowSearch), [preview.rows, rowFilter, rowSearch])

  return (
    <div className="space-y-5">
      <SummaryGrid summary={preview.summary} locale={locale} />

      {preview.has_errors && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-100">
          {text(locale, '请修正错误后重新上传', 'Fix the errors and upload again')}
        </p>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <input
          value={rowSearch}
          onChange={(event) => onSearchChange(event.target.value)}
          className="h-9 rounded-lg border border-border bg-background px-3 text-sm outline-none focus:border-foreground sm:w-[260px]"
          placeholder={text(locale, '搜索行、标题、目录或错误', 'Search row, title, path, or error')}
        />
        <div className="flex flex-wrap gap-1 rounded-lg bg-muted p-1">
          {(['all', 'error', 'create', 'update', 'skip'] as RowFilter[]).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => onFilterChange(item)}
              className={cn(
                'h-7 rounded-md px-2.5 text-xs font-medium transition-colors',
                rowFilter === item ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {item === 'all' ? text(locale, '全部', 'All') : actionLabel(item, locale)}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left text-muted-foreground">
            <tr>
              <th className="w-16 px-3 py-2 font-medium">{text(locale, '行', 'Row')}</th>
              <th className="w-20 px-3 py-2 font-medium">{text(locale, '动作', 'Action')}</th>
              <th className="px-3 py-2 font-medium">{text(locale, '目录 / 标题', 'Path / Title')}</th>
              <th className="px-3 py-2 font-medium">{text(locale, '结果', 'Result')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.row_number}-${row.action}-${row.title ?? ''}`} className="border-t border-border">
                <td className="px-3 py-2">{row.row_number}</td>
                <td className="px-3 py-2">{actionLabel(row.action, locale)}</td>
                <td className="min-w-0 px-3 py-2">
                  <p className="truncate font-medium text-foreground">{row.title ?? '—'}</p>
                  <p className="truncate text-xs text-muted-foreground">{row.directory_path ?? '—'}</p>
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {row.errors.length > 0 ? row.errors.map((item) => errorLabel(item, locale)).join('；') : rowResultLabel(row, locale)}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-10 text-center text-muted-foreground">
                  {text(locale, '无匹配行', 'No matching rows')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function SummaryGrid({ summary, locale }: { summary: KnowledgeImportSummary; locale: Locale }) {
  const items = [
    [text(locale, '总行数', 'Rows'), summary.total_rows],
    [text(locale, '新建目录', 'New Directories'), summary.create_directories],
    [text(locale, '新建文档', 'New Articles'), summary.create_documents],
    [text(locale, '更新文档', 'Updated Articles'), summary.update_documents],
    [text(locale, '跳过', 'Skipped'), summary.skipped_rows],
    [text(locale, '错误', 'Errors'), summary.error_rows],
  ] as const
  return (
    <div className="grid gap-3 rounded-lg border border-border bg-muted/20 p-4 text-sm sm:grid-cols-3">
      {items.map(([label, value]) => (
        <div key={label}>
          <p className="text-muted-foreground">{label}</p>
          <p className="mt-1 font-medium text-foreground">{value}</p>
        </div>
      ))}
    </div>
  )
}

function filterRows(rows: KnowledgeImportRowResult[], filter: RowFilter, search: string): KnowledgeImportRowResult[] {
  const keyword = search.trim().toLowerCase()
  return rows.filter((row) => {
    if (filter !== 'all' && row.action !== filter) return false
    if (!keyword) return true
    return [
      String(row.row_number),
      row.id == null ? '' : String(row.id),
      row.directory_path ?? '',
      row.title ?? '',
      row.message ?? '',
      ...row.errors,
    ].some((value) => value.toLowerCase().includes(keyword))
  })
}

function rowResultLabel(row: KnowledgeImportRowResult, locale: Locale): string {
  if (row.action === 'create') return text(locale, '可新建', 'Ready to create')
  if (row.action === 'update') return text(locale, '可更新', 'Ready to update')
  if (row.action === 'skip') return text(locale, '空行跳过', 'Blank row skipped')
  return row.message ?? '—'
}
