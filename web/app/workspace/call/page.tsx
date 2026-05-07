'use client'

import { IconPhone } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export default function CallPage() {
  const { locale } = useLocaleStore()

  return (
    <div className="flex h-full items-center justify-center">
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-muted">
          <IconPhone size={32} className="text-muted-foreground" />
        </div>
        <h2 className="text-xl font-semibold text-foreground">
          {t('ws.call.title', locale)}
        </h2>
        <p className="text-sm text-muted-foreground">
          {t('ws.call.desc', locale)}
        </p>
      </div>
    </div>
  )
}
