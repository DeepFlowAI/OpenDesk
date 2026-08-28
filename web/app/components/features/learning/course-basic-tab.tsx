'use client'

import { useEffect, useRef, useState } from 'react'
import { IconUpload } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { LearningCourseDetail } from '@/models/learning'
import { useUpdateCourse, useUploadCourseCover } from '@/service/use-learning'

const COVER_MAX_BYTES = 2 * 1024 * 1024
const COVER_TYPES = new Set(['image/jpeg', 'image/png'])

function FormField({
  label,
  required,
  hint,
  error,
  children,
}: {
  label: string
  required?: boolean
  hint?: string
  error?: string
  children: React.ReactNode
}) {
  return (
    <div>
      <div className="mb-1.5 text-sm font-medium text-foreground">
        {label}
        {required ? <span className="ml-0.5 text-red-500">*</span> : null}
      </div>
      {children}
      {error ? (
        <p className="mt-1 text-xs text-red-500">{error}</p>
      ) : hint ? (
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  )
}

export function CourseBasicTab({ course }: { course: LearningCourseDetail }) {
  const { locale } = useLocaleStore()
  const [name, setName] = useState(course.name)
  const [intro, setIntro] = useState(course.intro ?? '')
  const [coverUrl, setCoverUrl] = useState(course.cover_url ?? '')
  const [nameError, setNameError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Reset the local form when switching between courses or after refetch.
  useEffect(() => {
    setName(course.name)
    setIntro(course.intro ?? '')
    setCoverUrl(course.cover_url ?? '')
    setNameError('')
  }, [course.id, course.name, course.intro, course.cover_url])

  const updateMutation = useUpdateCourse(course.id)
  const coverMutation = useUploadCourseCover()

  const validateName = (value: string): boolean => {
    const trimmed = value.trim()
    if (!trimmed || trimmed.length > 50) {
      setNameError(t('learning.basic.nameRequired', locale))
      return false
    }
    setNameError('')
    return true
  }

  const handleCoverChange = async (file: File | undefined) => {
    if (!file) return
    if (!COVER_TYPES.has(file.type) || file.size > COVER_MAX_BYTES) {
      toast.error(t('learning.basic.coverInvalid', locale))
      return
    }
    try {
      const result = await coverMutation.mutateAsync(file)
      setCoverUrl(result.url)
    } catch {
      toast.error(t('learning.common.loadFailed', locale))
    }
  }

  const handleSave = async () => {
    if (!validateName(name)) return
    try {
      await updateMutation.mutateAsync({
        name: name.trim(),
        intro: intro.trim(),
        cover_url: coverUrl,
      })
      toast.success(t('learning.toast.saved', locale))
    } catch {
      toast.error(t('learning.common.loadFailed', locale))
    }
  }

  const saving = updateMutation.isPending || coverMutation.isPending

  return (
    <div className="max-w-xl space-y-6 rounded-xl border border-border bg-white p-6">
      <FormField
        label={t('learning.basic.name', locale)}
        required
        hint={t('learning.basic.nameHint', locale)}
        error={nameError}
      >
        <input
          value={name}
          onChange={(event) => {
            setName(event.target.value)
            if (nameError) validateName(event.target.value)
          }}
          onBlur={() => validateName(name)}
          maxLength={50}
          className="h-10 w-full rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-primary"
        />
      </FormField>

      <FormField label={t('learning.basic.cover', locale)} hint={t('learning.basic.coverHint', locale)}>
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex h-24 w-40 items-center justify-center overflow-hidden rounded-md border border-dashed border-border bg-muted/40 text-muted-foreground"
          >
            {coverUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={coverUrl} alt={name} className="h-full w-full object-cover" />
            ) : (
              <IconUpload size={20} />
            )}
          </button>
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="h-8 rounded-md border border-border px-3 text-xs font-medium text-foreground/80 hover:bg-accent"
            >
              {coverUrl ? t('learning.basic.coverChange', locale) : t('learning.basic.cover', locale)}
            </button>
            {coverUrl ? (
              <button
                type="button"
                onClick={() => setCoverUrl('')}
                className="h-8 rounded-md px-3 text-xs text-red-600 hover:bg-red-50"
              >
                {t('learning.basic.coverRemove', locale)}
              </button>
            ) : null}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png"
            className="hidden"
            onChange={(event) => {
              void handleCoverChange(event.target.files?.[0])
              event.target.value = ''
            }}
          />
        </div>
      </FormField>

      <FormField label={t('learning.basic.intro', locale)} hint={t('learning.basic.introHint', locale)}>
        <textarea
          value={intro}
          onChange={(event) => setIntro(event.target.value)}
          maxLength={200}
          rows={5}
          className="w-full resize-none rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus:border-primary"
        />
      </FormField>

      <div className="flex justify-end border-t border-border pt-4">
        <button
          type="button"
          disabled={saving}
          onClick={() => void handleSave()}
          className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {saving ? '...' : t('learning.basic.save', locale)}
        </button>
      </div>
    </div>
  )
}
