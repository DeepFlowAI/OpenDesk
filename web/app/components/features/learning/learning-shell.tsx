'use client'

import type { ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { IconSchool } from '@tabler/icons-react'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { UserDropdown } from '@/app/components/features/user-dropdown'
import { hasPermission } from '@/utils/permissions'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'

/**
 * Standalone full-page shell for /learning: logo + title, internal tabs
 * (my learning / my exams / course admin / exam admin), account menu.
 */
export function LearningShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const { user } = useAuthStore()
  const { locale } = useLocaleStore()
  const canManageCourses = hasPermission(user, 'learning.course.manage')
  const canManageExams = hasPermission(user, 'learning.exam.manage')

  const tabs = [
    { key: 'my', labelKey: 'learning.tab.my', href: '/learning/my' },
    { key: 'myExams', labelKey: 'learning.tab.myExams', href: '/learning/exams/my' },
    ...(canManageCourses ? [{ key: 'courses', labelKey: 'learning.tab.courses', href: '/learning/courses' }] : []),
    ...(canManageExams ? [{ key: 'exams', labelKey: 'learning.tab.exams', href: '/learning/exams' }] : []),
  ]

  return (
    <div className="flex h-screen flex-col bg-muted/30 text-foreground">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <div className="flex self-stretch items-center gap-4">
          <div className="flex items-center gap-2">
            <IconSchool size={22} className="text-foreground" />
            <span className="text-base font-semibold">{t('learning.shell.title', locale)}</span>
          </div>
          <nav className="ml-6 flex items-stretch gap-1 self-stretch">
            {tabs.map((tab) => {
              // /learning/exams/my must not light up the admin exams tab.
              const active =
                tab.href === '/learning/exams'
                  ? pathname.startsWith('/learning/exams') && !pathname.startsWith('/learning/exams/my')
                  : pathname.startsWith(tab.href)
              return (
                <Link
                  key={tab.key}
                  href={tab.href}
                  className={cn(
                    '-mb-px flex items-center border-b-2 px-3 text-sm transition-colors',
                    active
                      ? 'border-primary font-semibold text-foreground'
                      : 'border-transparent text-muted-foreground hover:text-foreground',
                  )}
                >
                  {t(tab.labelKey, locale)}
                </Link>
              )
            })}
          </nav>
        </div>
        <UserDropdown />
      </header>
      <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
    </div>
  )
}
