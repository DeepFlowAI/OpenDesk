'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  IconArrowLeft,
  IconDeviceFloppy,
  IconFileText,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { RichTextFieldEditor } from '@/app/components/features/field-system/rich-text-field-editor'
import type {
  KnowledgeDirectoryNode,
  KnowledgeDocument,
  KnowledgeDocumentPayload,
  KnowledgeDocumentStatus,
  KnowledgeValidityType,
} from '@/models/knowledge'
import {
  flattenKnowledgeDirectories,
  fromDatetimeLocalValue,
  stripKnowledgeHtml,
  toDatetimeLocalValue,
} from './knowledge-utils'

type KnowledgeDocumentFormValues = {
  title: string
  directory_id: number | null
  status: KnowledgeDocumentStatus
  validity_type: KnowledgeValidityType
  valid_from: string
  valid_to: string
  content_html: string
}

type KnowledgeDocumentFormProps = {
  mode: 'create' | 'edit'
  directories: KnowledgeDirectoryNode[]
  document?: KnowledgeDocument | null
  initialDirectoryId?: number | null
  saving: boolean
  isZh: boolean
  onCancel: () => void
  onSubmit: (payload: KnowledgeDocumentPayload) => Promise<void>
}

function snapshot(values: KnowledgeDocumentFormValues): string {
  return JSON.stringify(values)
}

function initialValues(
  document: KnowledgeDocument | null | undefined,
  initialDirectoryId: number | null | undefined,
): KnowledgeDocumentFormValues {
  return {
    title: document?.title ?? '',
    directory_id: document?.directory_id ?? initialDirectoryId ?? null,
    status: document?.status ?? 'draft',
    validity_type: document?.validity_type ?? 'permanent',
    valid_from: toDatetimeLocalValue(document?.valid_from),
    valid_to: toDatetimeLocalValue(document?.valid_to),
    content_html: document?.content_html ?? '<p></p>',
  }
}

export function KnowledgeDocumentForm({
  mode,
  directories,
  document,
  initialDirectoryId = null,
  saving,
  isZh,
  onCancel,
  onSubmit,
}: KnowledgeDocumentFormProps) {
  const directoryOptions = useMemo(() => flattenKnowledgeDirectories(directories), [directories])
  const [values, setValues] = useState<KnowledgeDocumentFormValues>(() =>
    initialValues(document, initialDirectoryId),
  )
  const [initialSnapshot, setInitialSnapshot] = useState(() => snapshot(values))
  const [errors, setErrors] = useState<Partial<Record<keyof KnowledgeDocumentFormValues, string>>>({})
  const dirty = snapshot(values) !== initialSnapshot

  useEffect(() => {
    const next = initialValues(document, initialDirectoryId)
    setValues(next)
    setInitialSnapshot(snapshot(next))
    setErrors({})
  }, [document, initialDirectoryId])

  useEffect(() => {
    if (!dirty) return
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [dirty])

  const setField = <K extends keyof KnowledgeDocumentFormValues>(
    key: K,
    value: KnowledgeDocumentFormValues[K],
  ) => {
    setValues((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => {
      if (!prev[key]) return prev
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  const validate = (): boolean => {
    const next: Partial<Record<keyof KnowledgeDocumentFormValues, string>> = {}
    if (!values.title.trim()) next.title = isZh ? '请输入文档标题' : 'Title is required'
    if (!values.directory_id) next.directory_id = isZh ? '请选择目录' : 'Directory is required'
    if (!stripKnowledgeHtml(values.content_html)) {
      next.content_html = isZh ? '请输入正文内容' : 'Content is required'
    }
    if (values.validity_type === 'scheduled') {
      if (!values.valid_from) next.valid_from = isZh ? '请选择开始时间' : 'Start time is required'
      if (!values.valid_to) next.valid_to = isZh ? '请选择结束时间' : 'End time is required'
      if (values.valid_from && values.valid_to && values.valid_to <= values.valid_from) {
        next.valid_to = isZh ? '结束时间需晚于开始时间' : 'End time must be after start time'
      }
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const handleCancel = () => {
    if (dirty) {
      const ok = window.confirm(isZh ? '当前内容尚未保存，确定离开？' : 'You have unsaved changes. Leave anyway?')
      if (!ok) return
    }
    onCancel()
  }

  const handleSubmit = async () => {
    if (!validate() || !values.directory_id) return
    const payload: KnowledgeDocumentPayload = {
      title: values.title.trim(),
      directory_id: values.directory_id,
      content_html: values.content_html,
      status: values.status,
      validity_type: values.validity_type,
      valid_from: values.validity_type === 'scheduled' ? fromDatetimeLocalValue(values.valid_from) : null,
      valid_to: values.validity_type === 'scheduled' ? fromDatetimeLocalValue(values.valid_to) : null,
    }
    await onSubmit(payload)
    setInitialSnapshot(snapshot(values))
  }

  return (
    <div className="flex min-h-full flex-col bg-white">
      <div className="sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between border-b border-[#E5E5E5] bg-white px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={handleCancel}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-[#737373] transition-colors hover:bg-[#F5F5F5] hover:text-[#1A1A1A]"
            title={isZh ? '返回' : 'Back'}
          >
            <IconArrowLeft size={20} />
          </button>
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold text-[#1A1A1A]">
              {mode === 'edit' ? (isZh ? '编辑文档' : 'Edit Article') : (isZh ? '新建文档' : 'New Article')}
            </h1>
          </div>
        </div>

        <button
          type="button"
          onClick={handleSubmit}
          disabled={saving || directoryOptions.length === 0}
          className="flex h-9 items-center gap-2 rounded-lg bg-[#1A1A1A] px-4 text-sm font-medium text-white transition-colors hover:bg-black/85 disabled:opacity-50"
        >
          <IconDeviceFloppy size={16} />
          {saving ? (isZh ? '保存中' : 'Saving') : (isZh ? '保存' : 'Save')}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-8">
        <div className="mx-auto max-w-[920px] rounded-lg border border-[#E5E5E5] bg-white px-12 py-8">
          {directoryOptions.length === 0 ? (
            <div className="flex h-80 flex-col items-center justify-center text-center">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[#F5F5F5] text-[#999999]">
                <IconFileText size={24} />
              </div>
              <p className="text-sm text-[#737373]">
                {isZh ? '请先创建目录' : 'Create a directory first'}
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-[#404040]">
                  {isZh ? '标题' : 'Title'}
                </span>
                <input
                  value={values.title}
                  onChange={(event) => setField('title', event.target.value)}
                  maxLength={120}
                  className={cn(
                    'h-10 w-full rounded-lg border bg-white px-3 text-sm text-[#1A1A1A] outline-none transition-colors placeholder:text-[#999999] focus:border-[#1A1A1A]',
                    errors.title ? 'border-[#DC2626]' : 'border-[#E5E5E5]',
                  )}
                  placeholder={isZh ? '请输入文档标题' : 'Enter article title'}
                />
                {errors.title && <span className="mt-1 block text-xs text-[#DC2626]">{errors.title}</span>}
              </label>

              <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-[#404040]">
                    {isZh ? '目录' : 'Directory'}
                  </span>
                  <select
                    value={values.directory_id ?? ''}
                    onChange={(event) => setField('directory_id', event.target.value ? Number(event.target.value) : null)}
                    className={cn(
                      'h-10 w-full rounded-lg border bg-white px-3 text-sm text-[#1A1A1A] outline-none transition-colors focus:border-[#1A1A1A]',
                      errors.directory_id ? 'border-[#DC2626]' : 'border-[#E5E5E5]',
                    )}
                  >
                    <option value="">{isZh ? '请选择目录' : 'Select directory'}</option>
                    {directoryOptions.map((item) => (
                      <option key={item.node.id} value={item.node.id}>
                        {'　'.repeat(Math.max(0, item.depth - 1))}
                        {item.node.name}
                      </option>
                    ))}
                  </select>
                  {errors.directory_id && (
                    <span className="mt-1 block text-xs text-[#DC2626]">{errors.directory_id}</span>
                  )}
                </label>

                <div>
                  <span className="mb-2 block text-sm font-medium text-[#404040]">
                    {isZh ? '发布状态' : 'Status'}
                  </span>
                  <div className="inline-flex h-10 rounded-lg border border-[#E5E5E5] bg-[#FAFAFA] p-1">
                    {(['draft', 'published'] as const).map((status) => (
                      <button
                        key={status}
                        type="button"
                        onClick={() => setField('status', status)}
                        className={cn(
                          'h-8 rounded-md px-4 text-sm font-medium transition-colors',
                          values.status === status
                            ? 'bg-white text-[#1A1A1A] shadow-sm'
                            : 'text-[#737373] hover:text-[#1A1A1A]',
                        )}
                      >
                        {status === 'published' ? (isZh ? '发布' : 'Published') : (isZh ? '草稿' : 'Draft')}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div>
                <span className="mb-2 block text-sm font-medium text-[#404040]">
                  {isZh ? '有效期' : 'Validity'}
                </span>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="inline-flex h-10 rounded-lg border border-[#E5E5E5] bg-[#FAFAFA] p-1">
                    {(['permanent', 'scheduled'] as const).map((type) => (
                      <button
                        key={type}
                        type="button"
                        onClick={() => setField('validity_type', type)}
                        className={cn(
                          'h-8 rounded-md px-4 text-sm font-medium transition-colors',
                          values.validity_type === type
                            ? 'bg-white text-[#1A1A1A] shadow-sm'
                            : 'text-[#737373] hover:text-[#1A1A1A]',
                        )}
                      >
                        {type === 'permanent' ? (isZh ? '永久有效' : 'Permanent') : (isZh ? '指定时间' : 'Scheduled')}
                      </button>
                    ))}
                  </div>
                  {values.validity_type === 'scheduled' && (
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        type="datetime-local"
                        value={values.valid_from}
                        onChange={(event) => setField('valid_from', event.target.value)}
                        className={cn(
                          'h-10 rounded-lg border bg-white px-3 text-sm text-[#1A1A1A] outline-none focus:border-[#1A1A1A]',
                          errors.valid_from ? 'border-[#DC2626]' : 'border-[#E5E5E5]',
                        )}
                      />
                      <span className="text-sm text-[#999999]">-</span>
                      <input
                        type="datetime-local"
                        value={values.valid_to}
                        onChange={(event) => setField('valid_to', event.target.value)}
                        className={cn(
                          'h-10 rounded-lg border bg-white px-3 text-sm text-[#1A1A1A] outline-none focus:border-[#1A1A1A]',
                          errors.valid_to ? 'border-[#DC2626]' : 'border-[#E5E5E5]',
                        )}
                      />
                    </div>
                  )}
                </div>
                {(errors.valid_from || errors.valid_to) && (
                  <span className="mt-1 block text-xs text-[#DC2626]">
                    {errors.valid_from || errors.valid_to}
                  </span>
                )}
              </div>

              <div>
                <span className="mb-2 block text-sm font-medium text-[#404040]">
                  {isZh ? '正文内容' : 'Content'}
                </span>
                <RichTextFieldEditor
                  value={values.content_html}
                  onChange={(value) => setField('content_html', value ?? '<p></p>')}
                  typeConfig={{ rich_format: 'html' }}
                  placeholder={isZh ? '请输入正文内容' : 'Write the article'}
                  plainChrome
                  className={cn(
                    'min-h-[440px] rounded-lg border border-[#E5E5E5] bg-white [&_.ProseMirror]:min-h-[360px]',
                    errors.content_html && 'border-[#DC2626]',
                  )}
                />
                {errors.content_html && (
                  <span className="mt-1 block text-xs text-[#DC2626]">{errors.content_html}</span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
