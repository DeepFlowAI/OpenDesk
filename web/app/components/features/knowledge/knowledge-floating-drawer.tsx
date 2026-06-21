'use client'

import { useState } from 'react'
import { IconBook2 } from '@tabler/icons-react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { KnowledgeAssistant } from './knowledge-assistant'

type KnowledgeFloatingDrawerProps = {
  className?: string
}

export function KnowledgeFloatingDrawer({ className }: KnowledgeFloatingDrawerProps) {
  const { locale } = useLocaleStore()
  const [open, setOpen] = useState(false)

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={cn(
          'fixed right-0 top-1/2 z-40 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-l-full bg-primary text-primary-foreground shadow-lg transition-colors hover:bg-primary/90',
          className,
        )}
        aria-label={t('ws.knowledge.title', locale)}
        title={t('ws.knowledge.title', locale)}
      >
        <IconBook2 size={20} stroke={1.6} />
      </button>
      <SheetContent
        side="right"
        offsetWorkspaceHeader
        overlayClassName="hidden"
        className="w-[400px] gap-0 p-0 sm:max-w-[400px]"
      >
        <SheetHeader className="shrink-0 border-b border-border px-4 py-3">
          <SheetTitle>{t('ws.knowledge.title', locale)}</SheetTitle>
        </SheetHeader>
        <KnowledgeAssistant mode="drawer" showCopy className="min-h-0" />
      </SheetContent>
    </Sheet>
  )
}
