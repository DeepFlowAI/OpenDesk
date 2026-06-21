'use client'

import { useState } from 'react'
import { IconDownload } from '@tabler/icons-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

type ExportResult = {
  blob: Blob
  filename: string
}

type WorkspaceListExportProps = {
  allowed: boolean
  locale: string
  buttonLabel: string
  title: string
  description: string
  scopeLabel: string
  totalLabel: string
  columnsLabel: string
  formatLabel: string
  confirmLabel: string
  cancelLabel: string
  successMessage: string
  errorMessage: string
  onExport: () => Promise<ExportResult>
}

export function WorkspaceListExport({
  allowed,
  locale,
  buttonLabel,
  title,
  description,
  scopeLabel,
  totalLabel,
  columnsLabel,
  formatLabel,
  confirmLabel,
  cancelLabel,
  successMessage,
  errorMessage,
  onExport,
}: WorkspaceListExportProps) {
  const [open, setOpen] = useState(false)
  const [exporting, setExporting] = useState(false)

  if (!allowed) return null

  const handleExport = async () => {
    if (exporting) return
    setExporting(true)
    try {
      const result = await onExport()
      triggerDownload(result.blob, result.filename)
      toast.success(successMessage)
      setOpen(false)
    } catch {
      toast.error(errorMessage)
    } finally {
      setExporting(false)
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={exporting}
        className={cn(
          'flex h-9 items-center gap-1.5 rounded-lg border border-border px-3 text-sm transition-colors',
          exporting
            ? 'cursor-not-allowed opacity-50'
            : 'text-foreground/80 hover:bg-accent',
        )}
      >
        <IconDownload size={16} className={exporting ? 'animate-pulse' : ''} />
        {exporting ? (locale === 'zh' ? '导出中' : 'Exporting') : buttonLabel}
      </button>

      <Dialog open={open} onOpenChange={(nextOpen) => !exporting && setOpen(nextOpen)}>
        <DialogContent className="sm:max-w-[460px]">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>

          <div className="grid gap-3 rounded-lg border border-border bg-muted/30 p-3 text-sm">
            <InfoRow label={locale === 'zh' ? '当前范围' : 'Current scope'} value={scopeLabel} />
            <InfoRow label={locale === 'zh' ? '结果数量' : 'Result count'} value={totalLabel} />
            <InfoRow label={locale === 'zh' ? '导出列' : 'Export columns'} value={columnsLabel} />
            <InfoRow label={locale === 'zh' ? '文件格式' : 'File format'} value={formatLabel} />
          </div>

          <DialogFooter className="border-t-0 pb-0">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={exporting}
            >
              {cancelLabel}
            </Button>
            <Button type="button" onClick={handleExport} disabled={exporting}>
              {exporting ? (locale === 'zh' ? '导出中' : 'Exporting') : confirmLabel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[96px_1fr] gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 break-words text-foreground">{value}</span>
    </div>
  )
}

function triggerDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename || 'export.xlsx'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.URL.revokeObjectURL(url)
}
