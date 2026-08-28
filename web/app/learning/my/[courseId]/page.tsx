'use client'

import dynamic from 'next/dynamic'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  IconArrowLeft,
  IconCheck,
  IconChevronLeft,
  IconChevronRight,
  IconDownload,
  IconFileText,
  IconLoader2,
  IconMusic,
  IconVideo,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  useCompleteMaterial,
  useMyCourseDetail,
  useOpenMaterial,
  useReportProgress,
} from '@/service/use-learning'
import type { MaterialOpenResponse, MaterialType, MyMaterialItem } from '@/models/learning'
import { formatDurationSeconds } from '@/app/components/features/learning/learning-tags'
import { JitDocumentViewer } from '@/app/components/features/file-preview/jit-document-viewer'
import { cn } from '@/lib/utils'

const PDFViewer = dynamic(
  () => import('@embedpdf/react-pdf-viewer').then((mod) => mod.PDFViewer),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full w-full items-center justify-center">
        <IconLoader2 size={18} className="animate-spin text-muted-foreground" />
      </div>
    ),
  },
)

const PDFIUM_WASM_PATH = '/vendor/embedpdf/pdfium.wasm'

/** Keep zoom / pan / search / thumbnails; hide edit and file IO tools. */
const PDF_READER_DISABLED_CATEGORIES = [
  'annotation',
  'form',
  'redaction',
  'insert',
  'history',
  'security',
  'panel-comment',
  'document-open',
  'document-close',
  'document-print',
  'document-capture',
  'document-export',
  'document-protect',
]

const TYPE_ICON: Record<MaterialType, typeof IconVideo> = {
  video: IconVideo,
  audio: IconMusic,
  pdf: IconFileText,
  document: IconFileText,
}

const TYPE_TONE: Record<MaterialType, string> = {
  video: 'bg-sky-50 text-sky-700',
  audio: 'bg-violet-50 text-violet-700',
  pdf: 'bg-orange-50 text-orange-700',
  document: 'bg-amber-50 text-amber-700',
}

export default function CoursePlayerPage() {
  const router = useRouter()
  const params = useParams<{ courseId: string }>()
  const { locale } = useLocaleStore()
  const courseId = Number(params.courseId)

  const { data: course, isLoading, isError, refetch } = useMyCourseDetail(
    Number.isFinite(courseId) ? courseId : null,
  )
  const openMutation = useOpenMaterial()
  const reportMutation = useReportProgress()
  const completeMutation = useCompleteMaterial()

  const [activeMaterialId, setActiveMaterialId] = useState<number | null>(null)
  const [openMap, setOpenMap] = useState<Record<number, MaterialOpenResponse>>({})
  const [currentPos, setCurrentPos] = useState(0)
  const mediaRef = useRef<HTMLVideoElement | HTMLAudioElement | null>(null)
  const lastReportedRef = useRef(0)
  const openingRef = useRef<Set<number>>(new Set())
  const autoOpenTriedRef = useRef<Set<number>>(new Set())

  const flatMaterials = useMemo(
    () => (course?.sections ?? []).flatMap((section) => section.materials),
    [course],
  )

  useEffect(() => {
    if (activeMaterialId == null && flatMaterials.length > 0) {
      setActiveMaterialId(flatMaterials[0].id)
    }
  }, [activeMaterialId, flatMaterials])

  const activeMaterial = flatMaterials.find((m) => m.id === activeMaterialId) ?? null
  const activeIndex = activeMaterial ? flatMaterials.indexOf(activeMaterial) : -1
  const openData = activeMaterial ? openMap[activeMaterial.id] : undefined

  const selectMaterial = useCallback(
    async (material: MyMaterialItem) => {
      setActiveMaterialId(material.id)
      setCurrentPos(0)
      lastReportedRef.current = 0
      if (openMap[material.id] || openingRef.current.has(material.id)) return
      openingRef.current.add(material.id)
      try {
        const opened = await openMutation.mutateAsync(material.id)
        setOpenMap((prev) => ({ ...prev, [material.id]: opened }))
      } catch {
        toast.error(t('learning.common.loadFailed', locale))
      } finally {
        openingRef.current.delete(material.id)
      }
    },
    [openMap, openMutation, locale],
  )

  useEffect(() => {
    if (activeMaterialId != null && !openMap[activeMaterialId] && flatMaterials.length > 0) {
      const material = flatMaterials.find((m) => m.id === activeMaterialId)
      if (material && !autoOpenTriedRef.current.has(material.id)) {
        autoOpenTriedRef.current.add(material.id)
        void selectMaterial(material)
      }
    }
  }, [activeMaterialId, openMap, flatMaterials, selectMaterial])

  const durationSeconds = activeMaterial?.duration_seconds ?? 0
  const basePos = Math.max(openData?.play_position_seconds ?? 0, currentPos)
  const percent =
    durationSeconds > 0 ? Math.min(100, Math.round((basePos / durationSeconds) * 100)) : 0
  const recordStatus = openData?.record_status ?? activeMaterial?.my_status ?? 'not_started'
  const isCompleted = recordStatus === 'completed'
  const isMedia = activeMaterial?.type === 'video' || activeMaterial?.type === 'audio'
  const canConfirm = !isCompleted && (!isMedia || percent >= 90)

  const reportProgress = useCallback(
    (position: number, force = false) => {
      if (!activeMaterial || !isMedia) return
      const pos = Math.floor(position)
      if (!force && pos - lastReportedRef.current < 5) return
      lastReportedRef.current = pos
      reportMutation.mutate({ materialId: activeMaterial.id, positionSeconds: pos })
    },
    [activeMaterial, isMedia, reportMutation],
  )

  const handleConfirm = async () => {
    if (!activeMaterial) return
    try {
      await completeMutation.mutateAsync(activeMaterial.id)
      setOpenMap((prev) =>
        prev[activeMaterial.id]
          ? {
              ...prev,
              [activeMaterial.id]: { ...prev[activeMaterial.id], record_status: 'completed' },
            }
          : prev,
      )
      toast.success(t('learning.toast.materialCompleted', locale))
    } catch {
      toast.error(t('learning.common.loadFailed', locale))
    }
  }

  const playUrl = openData?.play_url ?? null
  const fileUrl = openData?.file_url ?? null
  const isMockMedia = Boolean(playUrl?.startsWith('mock://') || fileUrl?.startsWith('mock://'))

  const renderMedia = () => {
    if (!activeMaterial || !openData) return null
    if (isMockMedia) {
      return (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
          {t('learning.player.mockMedia', locale)}
        </div>
      )
    }
    if (activeMaterial.type === 'video') {
      if (activeMaterial.transcode_status === 'processing') {
        return (
          <div className="flex h-full min-h-[200px] w-full items-center justify-center rounded-lg bg-neutral-900 text-sm text-white/70">
            {t('learning.player.processing', locale)}
          </div>
        )
      }
      if (activeMaterial.transcode_status === 'failed') {
        return (
          <div className="flex h-full min-h-[200px] w-full items-center justify-center rounded-lg bg-neutral-900 text-sm text-white/70">
            {t('learning.player.transcodeFailed', locale)}
          </div>
        )
      }
      if (!playUrl) return null
      return (
        <div className="flex h-full min-h-0 w-full items-center justify-center">
          <video
            key={activeMaterial.id}
            ref={(node) => {
              mediaRef.current = node
            }}
            src={playUrl}
            controls
            className="max-h-full max-w-full rounded-lg bg-black object-contain"
            onLoadedMetadata={(event) => {
              const startAt = openData.play_position_seconds
              if (startAt > 0 && startAt < event.currentTarget.duration - 2) {
                event.currentTarget.currentTime = startAt
              }
            }}
            onTimeUpdate={(event) => {
              setCurrentPos(event.currentTarget.currentTime)
              reportProgress(event.currentTarget.currentTime)
            }}
            onPause={(event) => reportProgress(event.currentTarget.currentTime, true)}
            onEnded={(event) => reportProgress(event.currentTarget.currentTime, true)}
            onError={() => toast.error(t('learning.player.mediaLoadFailed', locale))}
          />
        </div>
      )
    }
    if (activeMaterial.type === 'audio') {
      if (!playUrl) return null
      return (
        <audio
          key={activeMaterial.id}
          ref={(node) => {
            mediaRef.current = node
          }}
          src={playUrl}
          controls
          className="w-full"
          onLoadedMetadata={(event) => {
            const startAt = openData.play_position_seconds
            if (startAt > 0 && startAt < event.currentTarget.duration - 2) {
              event.currentTarget.currentTime = startAt
            }
          }}
          onTimeUpdate={(event) => {
            setCurrentPos(event.currentTarget.currentTime)
            reportProgress(event.currentTarget.currentTime)
          }}
          onPause={(event) => reportProgress(event.currentTarget.currentTime, true)}
          onEnded={(event) => reportProgress(event.currentTarget.currentTime, true)}
          onError={() => toast.error(t('learning.player.mediaLoadFailed', locale))}
        />
      )
    }
    if (activeMaterial.type === 'pdf') {
      if (!fileUrl) return null
      return (
        <div
          key={activeMaterial.id}
          className="flex h-full min-h-[320px] w-full flex-col overflow-hidden rounded-lg border border-border bg-white"
        >
          <PDFViewer
            config={{
              src: fileUrl,
              wasmUrl: new URL(PDFIUM_WASM_PATH, window.location.origin).href,
              tabBar: 'never',
              theme: { preference: 'light' },
              disabledCategories: PDF_READER_DISABLED_CATEGORIES,
            }}
            className="min-h-0 flex-1 bg-white"
          />
        </div>
      )
    }
    if (activeMaterial.type === 'document') {
      if (!fileUrl) return null
      return (
        <div
          key={activeMaterial.id}
          className="h-full min-h-[320px] w-full overflow-hidden rounded-lg border border-border bg-white"
        >
          <JitDocumentViewer
            url={fileUrl}
            filename={openData?.file_name || `${activeMaterial.name}.docx`}
          />
        </div>
      )
    }
    return null
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        {t('learning.common.loading', locale)}
      </div>
    )
  }
  if (isError || !course) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <p className="text-sm text-muted-foreground">{t('learning.common.loadFailed', locale)}</p>
        <button
          type="button"
          onClick={() => refetch()}
          className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
        >
          {t('learning.common.retry', locale)}
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-white dark:bg-card">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-border px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => router.push('/learning/my')}
            className="flex shrink-0 items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <IconArrowLeft size={16} />
            <span>{t('learning.player.back', locale)}</span>
          </button>
          <span className="h-4 w-px shrink-0 bg-border" />
          <h1 className="truncate text-sm font-semibold">{course.name}</h1>
        </div>
        <span className="shrink-0 text-xs text-muted-foreground">
          {t('learning.player.completedSummary', locale, {
            done: String(course.completed_count),
            total: String(course.material_count),
          })}
        </span>
      </header>
      <div className="flex min-h-0 flex-1">
        <aside className="flex w-[300px] shrink-0 flex-col gap-1 overflow-y-auto border-r border-border bg-white px-3 py-4 dark:bg-card">
          {course.sections.map((section) => (
            <div key={section.id} className="mb-2">
              <div className="px-2.5 py-2 text-xs font-semibold">{section.name}</div>
              <div className="flex flex-col gap-0.5">
                {section.materials.map((material) => {
                  const TypeIcon = TYPE_ICON[material.type]
                  const done =
                    (openMap[material.id]?.record_status ?? material.my_status) === 'completed'
                  return (
                    <button
                      key={material.id}
                      type="button"
                      onClick={() => void selectMaterial(material)}
                      className={cn(
                        'flex items-center gap-2 rounded-md px-2.5 py-2 text-left text-xs',
                        material.id === activeMaterialId
                          ? 'bg-primary/8 font-medium text-foreground'
                          : 'text-foreground/80 hover:bg-accent',
                      )}
                    >
                      <TypeIcon size={14} className="shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate" title={material.name}>
                        {material.name}
                      </span>
                      {formatDurationSeconds(material.duration_seconds) ? (
                        <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                          {formatDurationSeconds(material.duration_seconds)}
                        </span>
                      ) : null}
                      {done ? (
                        <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-emerald-500 text-white">
                          <IconCheck size={10} stroke={3} />
                        </span>
                      ) : null}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </aside>
        <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          {activeMaterial ? (
            <>
              <div className="shrink-0 px-8 pt-5 pb-3">
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-semibold">{activeMaterial.name}</h2>
                  <span className={cn('rounded-md px-2 py-0.5 text-[11px]', TYPE_TONE[activeMaterial.type])}>
                    {t(`learning.materialType.${activeMaterial.type}`, locale)}
                  </span>
                </div>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto px-8">
                {renderMedia()}
              </div>
              <div className="shrink-0 border-t border-border bg-white px-8 py-4 dark:bg-card">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    {(activeMaterial.type === 'pdf' || activeMaterial.type === 'document') &&
                    openData?.download_url ? (
                      <a
                        href={openData.download_url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex h-9 items-center gap-1.5 rounded-md px-3 text-sm text-muted-foreground hover:text-foreground"
                      >
                        <IconDownload size={16} />
                        {t('learning.player.downloadRaw', locale)}
                      </a>
                    ) : null}
                  </div>
                  {isCompleted ? (
                    <button
                      type="button"
                      disabled
                      className="flex h-9 cursor-not-allowed items-center gap-1.5 rounded-md bg-muted px-4 text-sm font-medium text-muted-foreground"
                    >
                      <IconCheck size={16} />
                      {t('learning.player.completed', locale)}
                    </button>
                  ) : isMedia && percent < 90 ? (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {t('learning.player.confirmHintLocked', locale, {
                          percent: String(percent),
                        })}
                      </span>
                      <button
                        type="button"
                        disabled
                        className="h-9 cursor-not-allowed rounded-md bg-primary/40 px-4 text-sm font-medium text-primary-foreground"
                      >
                        {t('learning.player.confirm', locale)}
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      {isMedia ? (
                        <span className="text-xs text-emerald-600">
                          {t('learning.player.confirmHintReady', locale, {
                            percent: String(percent),
                          })}
                        </span>
                      ) : null}
                      <button
                        type="button"
                        disabled={completeMutation.isPending || !canConfirm}
                        onClick={() => void handleConfirm()}
                        className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60"
                      >
                        {t('learning.player.confirm', locale)}
                      </button>
                    </div>
                  )}
                </div>
                <div className="flex items-center justify-between">
                  <button
                    type="button"
                    disabled={activeIndex <= 0}
                    onClick={() => void selectMaterial(flatMaterials[activeIndex - 1])}
                    className="flex h-9 items-center gap-1 rounded-md border border-border bg-white px-3 text-sm disabled:opacity-50 dark:bg-card"
                  >
                    <IconChevronLeft size={16} />
                    {t('learning.player.prev', locale)}
                  </button>
                  <button
                    type="button"
                    disabled={activeIndex < 0 || activeIndex >= flatMaterials.length - 1}
                    onClick={() => void selectMaterial(flatMaterials[activeIndex + 1])}
                    className="flex h-9 items-center gap-1 rounded-md border border-border bg-white px-3 text-sm disabled:opacity-50 dark:bg-card"
                  >
                    {t('learning.player.next', locale)}
                    <IconChevronRight size={16} />
                  </button>
                </div>
              </div>
            </>
          ) : (
            <p className="px-8 py-5 text-sm text-muted-foreground">{t('learning.my.empty', locale)}</p>
          )}
        </section>
      </div>
    </div>
  )
}
