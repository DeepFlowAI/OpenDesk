'use client'

import { useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { IconFileUpload, IconLoader2 } from '@tabler/icons-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import {
  useExecuteSmsBulkImport,
  useParseSmsBulkImport,
  useValidateSmsBulkImport,
} from '@/service/use-sms-bulk-tasks'
import type {
  SmsBulkImportParseResponse,
  SmsBulkImportValidateResponse,
  SmsBulkTemplateItem,
} from '@/models/sms-bulk-task'

type Step = 'upload' | 'mapping' | 'validate' | 'preview'

const STEPS: { key: Step; label: string }[] = [
  { key: 'upload', label: '上传文件' },
  { key: 'mapping', label: '字段映射' },
  { key: 'validate', label: '数据校验' },
  { key: 'preview', label: '预览确认' },
]

const PHONE_HEADER_HINTS = ['手机号', '手机', '电话', '号码', 'phone', 'mobile', 'tel']
const MAX_FILE_SIZE = 10 * 1024 * 1024

/** Guess the mapping for a file column: phone column or template variable. */
function guessColumnMapping(header: string, template: SmsBulkTemplateItem): string {
  const normalized = header.trim().toLowerCase()
  if (PHONE_HEADER_HINTS.some((hint) => normalized.includes(hint))) return '__phone__'
  const variable = template.variables.find(
    (v) => v.key.toLowerCase() === normalized || v.label === header.trim(),
  )
  if (variable) return `var:${variable.key}`
  return ''
}

export function SmsTaskImportDialog({
  taskId,
  template,
  open,
  onClose,
}: {
  taskId: number
  template: SmsBulkTemplateItem
  open: boolean
  onClose: () => void
}) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [step, setStep] = useState<Step>('upload')
  const [parseResult, setParseResult] = useState<SmsBulkImportParseResponse | null>(null)
  const [columnMappings, setColumnMappings] = useState<Record<string, string>>({})
  const [validateResult, setValidateResult] = useState<SmsBulkImportValidateResponse | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const parseImport = useParseSmsBulkImport()
  const validateImport = useValidateSmsBulkImport()
  const executeImport = useExecuteSmsBulkImport(taskId)

  const stepIndex = STEPS.findIndex((s) => s.key === step)

  const phoneColumn = useMemo(
    () => Object.entries(columnMappings).find(([, target]) => target === '__phone__')?.[0] ?? '',
    [columnMappings],
  )
  const variableColumns = useMemo(() => {
    const result: Record<string, string> = {}
    Object.entries(columnMappings).forEach(([column, target]) => {
      if (target.startsWith('var:')) result[target.slice(4)] = column
    })
    return result
  }, [columnMappings])

  const reset = () => {
    setStep('upload')
    setParseResult(null)
    setColumnMappings({})
    setValidateResult(null)
    setSubmitting(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const handleFileChange = async (file: File | null) => {
    if (!file) return
    const name = file.name.toLowerCase()
    if (!name.endsWith('.csv') && !name.endsWith('.xlsx')) {
      toast.error('仅支持 CSV 或 XLSX 文件')
      return
    }
    if (file.size > MAX_FILE_SIZE) {
      toast.error('文件大小不能超过 10MB')
      return
    }
    try {
      const result = await parseImport.mutateAsync({ taskId, file })
      setParseResult(result)
      const initial: Record<string, string> = {}
      result.headers.forEach((header) => {
        initial[header] = guessColumnMapping(header, template)
      })
      setColumnMappings(initial)
      setStep('mapping')
    } catch {
      toast.error('文件解析失败，请检查文件格式')
    }
  }

  const mappingError = useMemo(() => {
    if (!phoneColumn) return '请选择接收号码对应的列'
    const missing = template.variables.filter((v) => v.required && !variableColumns[v.key])
    if (missing.length > 0) return `必填变量未映射：${missing.map((v) => v.label).join('、')}`
    return null
  }, [phoneColumn, template.variables, variableColumns])

  const handleValidate = async () => {
    if (!parseResult || mappingError) return
    setSubmitting(true)
    try {
      const result = await validateImport.mutateAsync({
        taskId,
        data: { token: parseResult.token, phone_column: phoneColumn, variable_columns: variableColumns },
      })
      setValidateResult(result)
      setStep('validate')
    } catch {
      toast.error('校验失败，请重新上传文件后重试')
    } finally {
      setSubmitting(false)
    }
  }

  const handleExecute = async () => {
    if (!parseResult) return
    setSubmitting(true)
    try {
      const result = await executeImport.mutateAsync({
        token: parseResult.token,
        phone_column: phoneColumn,
        variable_columns: variableColumns,
      })
      toast.success(`导入完成：成功 ${result.success} 条，跳过重复 ${result.duplicate} 条，失败 ${result.failed} 条`)
      handleClose()
    } catch {
      toast.error('导入失败，请重新上传文件后重试')
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) handleClose() }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>导入发送对象</DialogTitle>
          <DialogDescription>支持 CSV / XLSX 文件，单次不超过 10MB</DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-2 py-2">
          {STEPS.map((s, i) => (
            <div key={s.key} className="flex items-center gap-2">
              <span
                className={cn(
                  'flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium',
                  i < stepIndex && 'bg-success/10 text-success',
                  i === stepIndex && 'bg-primary text-primary-foreground',
                  i > stepIndex && 'bg-muted text-muted-foreground',
                )}
              >
                {i + 1}
              </span>
              <span className={cn('text-sm', i === stepIndex ? 'font-medium text-foreground' : 'text-muted-foreground')}>
                {s.label}
              </span>
              {i < STEPS.length - 1 && <span className="mx-1 h-px w-6 bg-border" />}
            </div>
          ))}
        </div>

        {step === 'upload' && (
          <div className="py-4">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx"
              className="hidden"
              onChange={(e) => void handleFileChange(e.target.files?.[0] ?? null)}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={parseImport.isPending}
              className="flex h-40 w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-muted/20 text-sm text-muted-foreground hover:bg-muted/40"
            >
              {parseImport.isPending ? (
                <IconLoader2 size={24} className="animate-spin" />
              ) : (
                <IconFileUpload size={24} />
              )}
              {parseImport.isPending ? '解析中...' : '点击选择文件'}
            </button>
            <p className="mt-3 text-xs text-muted-foreground">
              第一行为表头；需包含接收号码列{template.variables.length > 0 ? '，以及各模板变量对应的列' : ''}。
            </p>
          </div>
        )}

        {step === 'mapping' && parseResult && (
          <div className="max-h-[320px] overflow-auto py-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-2 py-2">文件列</th>
                  <th className="px-2 py-2">示例值</th>
                  <th className="px-2 py-2">映射为</th>
                </tr>
              </thead>
              <tbody>
                {parseResult.headers.map((header, colIndex) => (
                  <tr key={header} className="border-b border-border last:border-0">
                    <td className="px-2 py-2 font-medium">{header}</td>
                    <td className="max-w-[160px] truncate px-2 py-2 text-muted-foreground">
                      {parseResult.sample_rows[0]?.[colIndex] ?? '-'}
                    </td>
                    <td className="px-2 py-2">
                      <select
                        value={columnMappings[header] ?? ''}
                        onChange={(e) =>
                          setColumnMappings((prev) => ({ ...prev, [header]: e.target.value }))
                        }
                        className="h-8 w-full rounded-md border border-border bg-background px-2 text-sm"
                      >
                        <option value="">不导入</option>
                        <option value="__phone__">接收号码</option>
                        {template.variables.map((v) => (
                          <option key={v.key} value={`var:${v.key}`}>
                            变量 {`{${v.key}}`} · {v.label}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {mappingError && <p className="mt-2 text-xs text-destructive">{mappingError}</p>}
          </div>
        )}

        {step === 'validate' && validateResult && (
          <div className="py-2">
            <div className="mb-3 grid grid-cols-4 gap-3 text-center">
              <div className="rounded-md border border-border px-2 py-3">
                <div className="text-lg font-semibold">{validateResult.total}</div>
                <div className="text-xs text-muted-foreground">总行数</div>
              </div>
              <div className="rounded-md border border-border px-2 py-3">
                <div className="text-lg font-semibold text-success">{validateResult.valid}</div>
                <div className="text-xs text-muted-foreground">有效</div>
              </div>
              <div className="rounded-md border border-border px-2 py-3">
                <div className="text-lg font-semibold text-warning">{validateResult.duplicate}</div>
                <div className="text-xs text-muted-foreground">重复</div>
              </div>
              <div className="rounded-md border border-border px-2 py-3">
                <div className="text-lg font-semibold text-destructive">{validateResult.invalid}</div>
                <div className="text-xs text-muted-foreground">错误</div>
              </div>
            </div>
            {validateResult.errors.length > 0 && (
              <div className="max-h-[200px] overflow-auto rounded-md border border-border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted text-left text-xs text-muted-foreground">
                      <th className="px-3 py-2">行号</th>
                      <th className="px-3 py-2">号码</th>
                      <th className="px-3 py-2">原因</th>
                    </tr>
                  </thead>
                  <tbody>
                    {validateResult.errors.map((err) => (
                      <tr key={err.row_number} className="border-b border-border last:border-0">
                        <td className="px-3 py-2">{err.row_number}</td>
                        <td className="px-3 py-2 font-mono text-xs">{err.phone || '-'}</td>
                        <td className="px-3 py-2 text-destructive">{err.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {validateResult.invalid > 0 && (
              <p className="mt-2 text-xs text-muted-foreground">
                存在错误行，继续导入将只导入有效行；也可以返回修改映射或文件。
              </p>
            )}
          </div>
        )}

        {step === 'preview' && validateResult && (
          <div className="rounded-md border border-border bg-muted/20 px-4 py-6 text-center text-sm">
            将导入 <span className="font-semibold text-success">{validateResult.valid}</span> 条发送对象，
            跳过重复 <span className="font-semibold text-warning">{validateResult.duplicate}</span> 条
            {validateResult.invalid > 0 && (
              <>，忽略错误 <span className="font-semibold text-destructive">{validateResult.invalid}</span> 条</>
            )}
          </div>
        )}

        <DialogFooter>
          {step === 'upload' && (
            <button type="button" onClick={handleClose} className="rounded-md border border-border px-4 py-2 text-sm">
              取消
            </button>
          )}
          {step === 'mapping' && (
            <>
              <button type="button" onClick={() => setStep('upload')} className="rounded-md border border-border px-4 py-2 text-sm">
                上一步
              </button>
              <button
                type="button"
                disabled={!!mappingError || submitting}
                onClick={() => void handleValidate()}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                {submitting ? '校验中...' : '下一步'}
              </button>
            </>
          )}
          {step === 'validate' && (
            <>
              <button type="button" onClick={() => setStep('mapping')} className="rounded-md border border-border px-4 py-2 text-sm">
                上一步
              </button>
              <button
                type="button"
                disabled={!validateResult || validateResult.valid === 0}
                onClick={() => setStep('preview')}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                下一步
              </button>
            </>
          )}
          {step === 'preview' && (
            <>
              <button type="button" onClick={() => setStep('validate')} className="rounded-md border border-border px-4 py-2 text-sm">
                上一步
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={() => void handleExecute()}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                {submitting ? '导入中...' : '确认导入'}
              </button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
