'use client'

import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  IconAlertCircle,
  IconArrowDown,
  IconArrowUp,
  IconCheck,
  IconFileText,
  IconLoader2,
  IconMusic,
  IconPencil,
  IconPlus,
  IconTrash,
  IconUpload,
  IconVideo,
  IconX,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type {
  LearningCourseDetail,
  LearningMaterial,
  LearningSectionWithMaterials,
  MaterialType,
} from '@/models/learning'
import {
  learningKeys,
  useCreateMaterial,
  useCreateSection,
  useDeleteMaterial,
  useDeleteSection,
  useRenameMaterial,
  useRenameSection,
  useReorderMaterials,
  useReorderSections,
  useRetranscodeMaterial,
  useUploadCredential,
} from '@/service/use-learning'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  buildMaterialPayload,
  detectMaterialType,
  putToPresignedUrl,
  readMediaDurationSeconds,
  uploadToVod,
} from './material-uploader'
import { formatDurationSeconds } from './learning-tags'

const TYPE_ICON: Record<MaterialType, typeof IconVideo> = {
  video: IconVideo,
  audio: IconMusic,
  pdf: IconFileText,
  document: IconFileText,
}

type UploadTask = {
  key: string
  filename: string
  progress: number
  status: 'uploading' | 'success' | 'error'
  cancel: () => void
}

function TranscodeBadge({
  material,
  onRetranscode,
  pending,
}: {
  material: LearningMaterial
  onRetranscode: () => void
  pending: boolean
}) {
  const { locale } = useLocaleStore()
  if (material.type !== 'video' || !material.transcode_status || material.transcode_status === 'ok') {
    return null
  }
  if (material.transcode_status === 'processing') {
    return (
      <span className="flex shrink-0 items-center gap-1 rounded-md bg-sky-50 px-2 py-0.5 text-[11px] text-sky-700 dark:bg-sky-950 dark:text-sky-300">
        <IconLoader2 size={12} className="animate-spin" />
        {t('learning.content.transcode.processing', locale)}
      </span>
    )
  }
  return (
    <button
      type="button"
      disabled={pending}
      onClick={onRetranscode}
      className="flex shrink-0 items-center gap-1 rounded-md bg-red-50 px-2 py-0.5 text-[11px] text-red-600 hover:bg-red-100 disabled:opacity-50 dark:bg-red-950 dark:text-red-300"
    >
      <IconAlertCircle size={12} />
      {t('learning.content.transcode.failed', locale)}
    </button>
  )
}

export function CourseContentTab({ course }: { course: LearningCourseDetail }) {
  const { locale } = useLocaleStore()
  const queryClient = useQueryClient()
  const [activeSectionId, setActiveSectionId] = useState<number | null>(null)
  const [renamingSectionId, setRenamingSectionId] = useState<number | null>(null)
  const [renamingMaterialId, setRenamingMaterialId] = useState<number | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [tasks, setTasks] = useState<UploadTask[]>([])
  const [confirm, setConfirm] = useState<
    | { kind: 'section'; section: LearningSectionWithMaterials }
    | { kind: 'material'; material: LearningMaterial }
    | null
  >(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const createSection = useCreateSection(course.id)
  const renameSection = useRenameSection(course.id)
  const reorderSections = useReorderSections(course.id)
  const deleteSection = useDeleteSection(course.id)
  const renameMaterial = useRenameMaterial(course.id)
  const reorderMaterials = useReorderMaterials(course.id)
  const deleteMaterial = useDeleteMaterial(course.id)
  const retranscodeMaterial = useRetranscodeMaterial(course.id)
  const uploadCredential = useUploadCredential()
  const createMaterial = useCreateMaterial(course.id)

  const sections = course.sections
  const activeSection =
    sections.find((section) => section.id === activeSectionId) ?? sections[0] ?? null

  const patchTask = (key: string, patch: Partial<UploadTask>) =>
    setTasks((prev) => prev.map((task) => (task.key === key ? { ...task, ...patch } : task)))

  const uploadOne = async (file: File) => {
    const detect = detectMaterialType(file)
    if (!detect.ok) {
      toast.error(
        detect.reason === 'size'
          ? t('learning.content.fileTooLarge', locale)
          : t('learning.content.unsupportedFormat', locale),
      )
      return
    }
    if (!activeSection) return
    const key = `${Date.now()}-${file.name}`
    const signal = { cancelled: false }
    setTasks((prev) => [
      ...prev,
      {
        key,
        filename: file.name,
        progress: 0,
        status: 'uploading',
        cancel: () => {
          signal.cancelled = true
          patchTask(key, { status: 'error' })
        },
      },
    ])
    try {
      const credential = await uploadCredential.mutateAsync({
        filename: file.name,
        file_size: file.size,
        material_type: detect.type,
      })
      const onProgress = (percent: number) => patchTask(key, { progress: percent })
      if (credential.channel === 'vod') {
        await uploadToVod(credential, file, onProgress)
      } else if (credential.upload_url) {
        await putToPresignedUrl(credential.upload_url, file, onProgress, signal)
      }
      if (signal.cancelled) return
      const duration =
        detect.type === 'video' || detect.type === 'audio'
          ? await readMediaDurationSeconds(file)
          : undefined
      await createMaterial.mutateAsync({
        sectionId: activeSection.id,
        payload: buildMaterialPayload(file, detect.type, credential, duration),
      })
      patchTask(key, { progress: 100, status: 'success' })
      setTimeout(() => setTasks((prev) => prev.filter((task) => task.key !== key)), 1500)
    } catch {
      patchTask(key, { status: 'error' })
    }
  }

  const moveSection = (index: number, direction: -1 | 1) => {
    const ids = sections.map((section) => section.id)
    const target = index + direction
    if (target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    reorderSections.mutate(ids)
  }

  const moveMaterial = (index: number, direction: -1 | 1) => {
    if (!activeSection) return
    const ids = activeSection.materials.map((material) => material.id)
    const target = index + direction
    if (target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    reorderMaterials.mutate({ sectionId: activeSection.id, orderedIds: ids })
  }

  const beginRenameSection = (section: LearningSectionWithMaterials) => {
    setActiveSectionId(section.id)
    setRenamingMaterialId(null)
    setRenamingSectionId(section.id)
    setRenameValue(section.name)
  }

  const commitRename = (kind: 'section' | 'material', id: number) => {
    const name = renameValue.trim()
    if (name) {
      if (kind === 'section') renameSection.mutate({ sectionId: id, name })
      else renameMaterial.mutate({ materialId: id, name })
    }
    setRenamingSectionId(null)
    setRenamingMaterialId(null)
    setRenameValue('')
  }

  const handleCreateSection = async () => {
    try {
      const section = await createSection.mutateAsync(undefined)
      const withMaterials: LearningSectionWithMaterials = { ...section, materials: [] }
      queryClient.setQueryData<LearningCourseDetail>(learningKeys.course(course.id), (prev) => {
        if (!prev) return prev
        if (prev.sections.some((item) => item.id === section.id)) return prev
        return { ...prev, sections: [...prev.sections, withMaterials] }
      })
      beginRenameSection(withMaterials)
    } catch {
      toast.error(t('learning.common.loadFailed', locale))
    }
  }

  const renameInput = (kind: 'section' | 'material', id: number, maxLength: number) => (
    <input
      autoFocus
      value={renameValue}
      maxLength={maxLength}
      placeholder={t('learning.content.renamePrompt', locale)}
      onFocus={(event) => event.target.select()}
      onChange={(event) => setRenameValue(event.target.value)}
      onBlur={() => commitRename(kind, id)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') commitRename(kind, id)
        if (event.key === 'Escape') {
          setRenamingSectionId(null)
          setRenamingMaterialId(null)
          setRenameValue('')
        }
      }}
      className="h-7 min-w-0 flex-1 rounded border border-primary/50 bg-white px-2 text-sm outline-none"
    />
  )

  return (
    <div className="flex gap-4">
      {/* Sections */}
      <aside className="flex w-64 shrink-0 flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-foreground">
            {t('learning.content.sections', locale)}
          </span>
          <button
            type="button"
            disabled={createSection.isPending}
            onClick={() => void handleCreateSection()}
            className="flex h-7 items-center gap-1 rounded-md border border-border bg-white px-2 text-xs text-muted-foreground hover:bg-accent disabled:opacity-50"
          >
            <IconPlus size={13} />
            {t('learning.content.addSection', locale)}
          </button>
        </div>
        {sections.map((section, index) => {
          const active = activeSection?.id === section.id
          return (
            <div
              key={section.id}
              onClick={() => setActiveSectionId(section.id)}
              className={`group flex cursor-pointer items-center gap-1.5 rounded-md border px-3 py-2.5 text-sm ${
                active
                  ? 'border-primary/40 bg-white font-medium'
                  : 'border-border bg-white/70 text-foreground/80 hover:bg-white'
              }`}
            >
              <span
                className="min-w-0 flex-1 truncate"
                title={
                  renamingSectionId === section.id ? renameValue || section.name : section.name
                }
              >
                {renamingSectionId === section.id ? renameValue || section.name : section.name}
              </span>
              <span className="flex shrink-0 items-center gap-1 text-muted-foreground">
                <button
                  type="button"
                  aria-label="move up"
                  disabled={index === 0}
                  onClick={(event) => {
                    event.stopPropagation()
                    moveSection(index, -1)
                  }}
                  className="opacity-0 hover:text-foreground disabled:opacity-30 group-hover:opacity-100"
                >
                  <IconArrowUp size={13} />
                </button>
                <button
                  type="button"
                  aria-label="move down"
                  disabled={index === sections.length - 1}
                  onClick={(event) => {
                    event.stopPropagation()
                    moveSection(index, 1)
                  }}
                  className="opacity-0 hover:text-foreground disabled:opacity-30 group-hover:opacity-100"
                >
                  <IconArrowDown size={13} />
                </button>
                <button
                  type="button"
                  aria-label={t('learning.content.renamePrompt', locale)}
                  onClick={(event) => {
                    event.stopPropagation()
                    beginRenameSection(section)
                  }}
                  className="hover:text-foreground"
                >
                  <IconPencil size={13} />
                </button>
                <button
                  type="button"
                  aria-label="delete"
                  onClick={(event) => {
                    event.stopPropagation()
                    setConfirm({ kind: 'section', section })
                  }}
                  className="text-red-500 opacity-0 hover:text-red-600 group-hover:opacity-100"
                >
                  <IconTrash size={13} />
                </button>
              </span>
            </div>
          )
        })}
      </aside>

      {/* Materials of the active section */}
      <section className="min-w-0 flex-1 rounded-xl border border-border bg-muted/20 p-4">
        {activeSection ? (
          <>
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="flex min-w-0 flex-1 items-center gap-1.5">
                {renamingSectionId === activeSection.id ? (
                  renameInput('section', activeSection.id, 30)
                ) : (
                  <>
                    <span className="min-w-0 truncate text-sm font-semibold text-foreground">
                      {activeSection.name}
                    </span>
                    <button
                      type="button"
                      aria-label={t('learning.content.renamePrompt', locale)}
                      onClick={() => beginRenameSection(activeSection)}
                      className="shrink-0 text-muted-foreground hover:text-foreground"
                    >
                      <IconPencil size={14} />
                    </button>
                  </>
                )}
              </div>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex h-8 shrink-0 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground"
              >
                <IconUpload size={14} />
                {t('learning.content.upload', locale)}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".mp4,.mov,.avi,.mkv,.flv,.mp3,.wav,.aac,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx"
                className="hidden"
                onChange={(event) => {
                  const files = Array.from(event.target.files ?? [])
                  files.forEach((file) => void uploadOne(file))
                  event.target.value = ''
                }}
              />
            </div>

            <div className="space-y-2">
              {activeSection.materials.map((material, index) => {
                const TypeIcon = TYPE_ICON[material.type]
                const duration = formatDurationSeconds(material.duration_seconds)
                return (
                  <div
                    key={material.id}
                    className="group flex items-center gap-2.5 rounded-md border border-border bg-white px-3 py-2.5"
                  >
                    <TypeIcon size={15} className="shrink-0 text-muted-foreground" />
                    {renamingMaterialId === material.id ? (
                      renameInput('material', material.id, 50)
                    ) : (
                      <span className="min-w-0 flex-1 truncate text-sm" title={material.name}>
                        {material.name}
                      </span>
                    )}
                    {duration ? (
                      <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                        {duration}
                      </span>
                    ) : null}
                    <TranscodeBadge
                      material={material}
                      pending={retranscodeMaterial.isPending}
                      onRetranscode={() =>
                        retranscodeMaterial.mutate(material.id, {
                          onSuccess: () =>
                            toast.success(t('learning.toast.retranscodeSubmitted', locale)),
                          onError: () => toast.error(t('learning.common.loadFailed', locale)),
                        })
                      }
                    />
                    <span className="flex shrink-0 items-center gap-1.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100">
                      <button
                        type="button"
                        aria-label="move up"
                        disabled={index === 0}
                        onClick={() => moveMaterial(index, -1)}
                        className="hover:text-foreground disabled:opacity-30"
                      >
                        <IconArrowUp size={14} />
                      </button>
                      <button
                        type="button"
                        aria-label="move down"
                        disabled={index === activeSection.materials.length - 1}
                        onClick={() => moveMaterial(index, 1)}
                        className="hover:text-foreground disabled:opacity-30"
                      >
                        <IconArrowDown size={14} />
                      </button>
                      <button
                        type="button"
                        aria-label="rename"
                        onClick={() => {
                          setRenamingMaterialId(material.id)
                          setRenameValue(material.name)
                        }}
                        className="hover:text-foreground"
                      >
                        <IconPencil size={14} />
                      </button>
                      <button
                        type="button"
                        aria-label="delete"
                        onClick={() => setConfirm({ kind: 'material', material })}
                        className="text-red-500 hover:text-red-600"
                      >
                        <IconTrash size={14} />
                      </button>
                    </span>
                  </div>
                )
              })}

              {tasks.map((task) => (
                <div
                  key={task.key}
                  className="flex items-center gap-2.5 rounded-md border border-dashed border-border bg-white/70 px-3 py-2.5"
                >
                  {task.status === 'success' ? (
                    <IconCheck size={15} className="shrink-0 text-emerald-600" />
                  ) : task.status === 'error' ? (
                    <IconAlertCircle size={15} className="shrink-0 text-red-500" />
                  ) : (
                    <IconLoader2 size={15} className="shrink-0 animate-spin text-primary" />
                  )}
                  <span className="min-w-0 flex-1 truncate text-sm" title={task.filename}>
                    {task.filename}
                  </span>
                  {task.status === 'uploading' ? (
                    <>
                      <div className="h-1.5 w-32 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-primary transition-all"
                          style={{ width: `${task.progress}%` }}
                        />
                      </div>
                      <span className="shrink-0 text-xs text-muted-foreground">{task.progress}%</span>
                      <button
                        type="button"
                        aria-label="cancel"
                        onClick={task.cancel}
                        className="shrink-0 text-muted-foreground hover:text-foreground"
                      >
                        <IconX size={14} />
                      </button>
                    </>
                  ) : task.status === 'error' ? (
                    <span className="shrink-0 text-xs text-red-500">
                      {t('learning.content.uploadFailed', locale)}
                    </span>
                  ) : null}
                </div>
              ))}

              {activeSection.materials.length === 0 && tasks.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  {t('learning.content.noMaterials', locale)}
                </p>
              ) : null}
            </div>
            <p className="mt-3 text-xs leading-5 text-muted-foreground">
              {t('learning.content.hint', locale)}
            </p>
          </>
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {t('learning.content.noMaterials', locale)}
          </p>
        )}
      </section>

      <ConfirmDialog
        open={confirm?.kind === 'section'}
        title={t('learning.confirm.deleteSection.title', locale)}
        message={
          confirm?.kind === 'section'
            ? t('learning.confirm.deleteSection.message', locale, {
                count: String(confirm.section.materials.length),
              })
            : undefined
        }
        itemName={confirm?.kind === 'section' ? confirm.section.name : undefined}
        confirmLabel={t('learning.confirm.deleteSection.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        variant="destructive"
        loading={deleteSection.isPending}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (confirm?.kind !== 'section') return
          try {
            await deleteSection.mutateAsync(confirm.section.id)
            toast.success(t('learning.toast.deleted', locale))
            if (activeSectionId === confirm.section.id) setActiveSectionId(null)
          } catch {
            toast.error(t('learning.common.loadFailed', locale))
          } finally {
            setConfirm(null)
          }
        }}
      />
      <ConfirmDialog
        open={confirm?.kind === 'material'}
        title={t('learning.confirm.deleteMaterial.title', locale)}
        message={t('learning.confirm.deleteMaterial.message', locale)}
        itemName={confirm?.kind === 'material' ? confirm.material.name : undefined}
        confirmLabel={t('learning.confirm.deleteMaterial.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        variant="destructive"
        loading={deleteMaterial.isPending}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (confirm?.kind !== 'material') return
          try {
            await deleteMaterial.mutateAsync(confirm.material.id)
            toast.success(t('learning.toast.deleted', locale))
          } catch {
            toast.error(t('learning.common.loadFailed', locale))
          } finally {
            setConfirm(null)
          }
        }}
      />
    </div>
  )
}
