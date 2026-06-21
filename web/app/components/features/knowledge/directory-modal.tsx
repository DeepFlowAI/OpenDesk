'use client'

import { useEffect, useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import type { KnowledgeDirectoryNode, KnowledgeDirectoryPayload } from '@/models/knowledge'
import {
  flattenKnowledgeDirectories,
  isKnowledgeDirectoryDescendant,
} from './knowledge-utils'

type DirectoryModalMode = 'create' | 'edit'

type DirectoryModalProps = {
  open: boolean
  mode: DirectoryModalMode
  directories: KnowledgeDirectoryNode[]
  directory?: KnowledgeDirectoryNode | null
  initialParentId?: number | null
  loading?: boolean
  isZh: boolean
  onClose: () => void
  onSubmit: (payload: KnowledgeDirectoryPayload) => Promise<void>
}

export function DirectoryModal({
  open,
  mode,
  directories,
  directory,
  initialParentId = null,
  loading = false,
  isZh,
  onClose,
  onSubmit,
}: DirectoryModalProps) {
  const [name, setName] = useState('')
  const [parentId, setParentId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setName(mode === 'edit' ? directory?.name ?? '' : '')
    setParentId(mode === 'edit' ? directory?.parent_id ?? null : initialParentId ?? null)
    setError(null)
  }, [directory, initialParentId, mode, open])

  const options = useMemo(() => {
    const flat = flattenKnowledgeDirectories(directories)
    if (mode !== 'edit' || !directory) return flat
    return flat.filter((item) => {
      if (item.node.id === directory.id) return false
      return !isKnowledgeDirectoryDescendant(directories, directory.id, item.node.id)
    })
  }, [directories, directory, mode])

  const handleSubmit = async () => {
    const normalized = name.trim()
    if (!normalized) {
      setError(isZh ? '请输入目录名称' : 'Directory name is required')
      return
    }
    await onSubmit({ name: normalized, parent_id: parentId })
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose() }}>
      <DialogContent
        className="w-[420px] max-w-[calc(100vw-32px)] gap-0 overflow-hidden rounded-xl bg-white p-0 shadow-[0_8px_24px_rgba(0,0,0,0.15)] sm:max-w-[420px]"
        overlayClassName="bg-black/20"
      >
        <DialogHeader className="border-b border-[#E5E5E5] px-6 py-5">
          <DialogTitle className="text-base font-semibold text-[#1A1A1A]">
            {mode === 'edit' ? (isZh ? '编辑目录' : 'Edit Directory') : (isZh ? '新建目录' : 'New Directory')}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-5 px-6 py-6">
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#404040]">
              {isZh ? '目录名称' : 'Directory Name'}
            </span>
            <input
              value={name}
              onChange={(event) => {
                setName(event.target.value)
                setError(null)
              }}
              maxLength={50}
              className={cn(
                'h-9 w-full rounded-lg border bg-white px-3 text-sm text-[#1A1A1A] outline-none transition-colors placeholder:text-[#999999] focus:border-[#1A1A1A]',
                error ? 'border-[#DC2626]' : 'border-[#E5E5E5]',
              )}
              placeholder={isZh ? '请输入目录名称' : 'Enter directory name'}
              autoFocus
            />
            {error && <span className="mt-1 block text-xs text-[#DC2626]">{error}</span>}
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#404040]">
              {isZh ? '父级目录' : 'Parent Directory'}
            </span>
            <select
              value={parentId ?? ''}
              onChange={(event) => setParentId(event.target.value ? Number(event.target.value) : null)}
              className="h-9 w-full rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1A1A1A] outline-none transition-colors focus:border-[#1A1A1A]"
            >
              <option value="">{isZh ? '一级目录' : 'Top level'}</option>
              {options.map((item) => (
                <option key={item.node.id} value={item.node.id}>
                  {'　'.repeat(Math.max(0, item.depth - 1))}
                  {item.node.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <DialogFooter className="border-t border-[#E5E5E5] px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="flex h-9 items-center rounded-lg border border-[#E5E5E5] px-4 text-sm font-medium text-[#404040] transition-colors hover:bg-[#F5F5F5] disabled:opacity-50"
          >
            {isZh ? '取消' : 'Cancel'}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={loading}
            className="flex h-9 items-center rounded-lg bg-[#1A1A1A] px-4 text-sm font-medium text-white transition-colors hover:bg-black/85 disabled:opacity-50"
          >
            {loading ? '...' : (isZh ? '确定' : 'Confirm')}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
