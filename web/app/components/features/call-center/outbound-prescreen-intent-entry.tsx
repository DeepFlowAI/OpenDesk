'use client'

import { useRouter } from 'next/navigation'
import { IconSettings } from '@tabler/icons-react'

import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export function OutboundPrescreenIntentEntry() {
  const router = useRouter()
  const { locale } = useLocaleStore()

  return (
    <section className="flex flex-col gap-4 border-t border-border pt-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-foreground">
            {t('prescreen.title', locale)}
          </h2>
          <p className="mt-1 max-w-[720px] text-sm leading-relaxed text-muted-foreground">
            {t('prescreen.desc', locale)}
          </p>
        </div>
        <Button
          size="lg"
          onClick={() => router.push('/call-center/settings/outbound-prescreen')}
        >
          <IconSettings size={17} />
          {t('prescreen.configure', locale)}
        </Button>
      </div>
    </section>
  )
}
