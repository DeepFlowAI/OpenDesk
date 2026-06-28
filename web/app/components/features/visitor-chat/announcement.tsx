'use client'

import { useEffect, useState, type MouseEvent } from 'react'
import { IconX } from '@tabler/icons-react'
import type { ConversationAnnouncementPublic } from '@/models/conversation-announcement'
import { ANNOUNCEMENT_BACKGROUND_VALUES } from '@/models/conversation-announcement'
import { SafeHtml } from '@/components/safe-html'
import { cn } from '@/lib/utils'

type VisitorAnnouncementProps = {
  announcement: ConversationAnnouncementPublic | null
  visible: boolean
  locale: string
  suppressAutoPopup?: boolean
}

function linkClick(event: MouseEvent<HTMLDivElement>) {
  const target = event.target
  if (!(target instanceof HTMLAnchorElement)) return
  const href = target.getAttribute('href')
  if (!href) return
  event.preventDefault()
  window.open(href, '_blank', 'noopener,noreferrer')
}

export function VisitorAnnouncement({
  announcement,
  visible,
  locale,
  suppressAutoPopup = false,
}: VisitorAnnouncementProps) {
  const [autoShownId, setAutoShownId] = useState<number | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [autoModal, setAutoModal] = useState(false)
  const [closingAuto, setClosingAuto] = useState(false)

  const hidden = !visible || !announcement

  useEffect(() => {
    if (!visible || !announcement) return
    if (suppressAutoPopup) return
    if (!announcement.auto_popup || autoShownId === announcement.id) return
    setModalOpen(true)
    setAutoModal(true)
    setAutoShownId(announcement.id)
  }, [announcement, autoShownId, suppressAutoPopup, visible])

  useEffect(() => {
    if (!visible) setModalOpen(false)
  }, [visible])

  if (!announcement || hidden) return null

  const background = ANNOUNCEMENT_BACKGROUND_VALUES[announcement.background_color]
  const closeModal = () => {
    if (!autoModal) {
      setModalOpen(false)
      return
    }
    setClosingAuto(true)
    window.setTimeout(() => {
      setModalOpen(false)
      setClosingAuto(false)
      setAutoModal(false)
    }, 240)
  }

  return (
    <>
      <div className="px-4 pb-1 pt-3">
        <div
          className="flex min-h-10 items-center gap-3 rounded-lg border border-black/10 px-3 py-2 text-sm text-stone-900 shadow-sm"
          style={{ backgroundColor: background }}
        >
          <SafeHtml
            html={announcement.summary_html}
            onClick={linkClick}
            className="min-w-0 flex-1 truncate leading-5 [&_*]:inline [&_a]:underline [&_br]:hidden [&_p]:m-0 [&_p]:inline"
          />
          <button
            type="button"
            onClick={() => {
              setModalOpen(true)
              setAutoModal(false)
            }}
            className="shrink-0 rounded-md px-2 py-1 text-xs font-semibold text-stone-800 hover:bg-black/5"
          >
            {locale === 'zh' ? '详情' : 'Details'}
          </button>
        </div>
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/35 p-4">
          <div
            className={cn(
              'relative max-h-[78%] w-full max-w-[520px] overflow-y-auto rounded-lg border border-black/10 p-5 text-stone-900 shadow-2xl transition duration-200 motion-reduce:transition-none',
              closingAuto && 'translate-y-6 scale-95 opacity-0 motion-reduce:translate-y-0 motion-reduce:scale-100',
            )}
            style={{ backgroundColor: background }}
          >
            <button
              type="button"
              onClick={closeModal}
              className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-lg text-stone-700 hover:bg-black/5"
              aria-label={locale === 'zh' ? '关闭公告详情' : 'Close announcement details'}
            >
              <IconX size={18} />
            </button>
            <SafeHtml
              html={announcement.detail_html}
              onClick={linkClick}
              className="prose prose-sm max-w-none pr-8 text-sm leading-6 text-stone-900 [&_a]:underline"
            />
          </div>
        </div>
      )}
    </>
  )
}
