'use client'

import Link from 'next/link'
import { IconShieldX } from '@tabler/icons-react'
import { LegalFooter } from '@/components/legal-footer'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { getDefaultAccessiblePath } from '@/utils/permissions'

export default function ForbiddenPage() {
  const { user } = useAuthStore()
  const { locale } = useLocaleStore()
  const homePath = getDefaultAccessiblePath(user)
  const targetPath = homePath === '/403' ? '/login' : homePath

  return (
    <main className="flex min-h-screen flex-col bg-background">
      <div className="flex flex-1 items-center justify-center px-6">
        <section className="flex max-w-md flex-col items-center gap-4 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <IconShieldX size={26} />
          </div>
          <div className="flex flex-col gap-2">
            <h1 className="text-2xl font-semibold text-foreground">{t('forbidden.title', locale)}</h1>
            <p className="text-sm leading-6 text-muted-foreground">
              {t('forbidden.description', locale)}
            </p>
          </div>
          <Link
            href={targetPath}
            className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {t('forbidden.action', locale)}
          </Link>
        </section>
      </div>
      <LegalFooter locale={locale} />
    </main>
  )
}
