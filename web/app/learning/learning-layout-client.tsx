'use client'

import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuthStore } from '@/context/auth-store'
import { useRefreshCurrentUser } from '@/hooks/use-refresh-current-user'
import { useApplyAccountLocale } from '@/hooks/use-apply-account-locale'
import { hasPermission } from '@/utils/permissions'
import { LearningShell } from '@/app/components/features/learning/learning-shell'

/** Admin exam pages live under /learning/exams except the employee-side my pages. */
function isExamAdminPath(pathname: string): boolean {
  return pathname.startsWith('/learning/exams') && !pathname.startsWith('/learning/exams/my')
}

export default function LearningLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { token, user } = useAuthStore()
  const [mounted, setMounted] = useState(false)
  const { isRefreshing: authRefreshing } = useRefreshCurrentUser(mounted)
  useApplyAccountLocale()

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (mounted && !token) {
      router.replace('/login')
    }
  }, [mounted, token, router])

  useEffect(() => {
    if (!mounted || !token || !user || authRefreshing) return
    if (!hasPermission(user, 'learning.center.use')) {
      router.replace('/403')
      return
    }
    // The management areas require the manage permission on top of use.
    if (pathname.startsWith('/learning/courses') && !hasPermission(user, 'learning.course.manage')) {
      router.replace('/learning/my')
      return
    }
    if (isExamAdminPath(pathname) && !hasPermission(user, 'learning.exam.manage')) {
      router.replace('/learning/my')
    }
  }, [authRefreshing, mounted, token, user, pathname, router])

  if (!mounted || authRefreshing || !token || !user) return null
  if (!hasPermission(user, 'learning.center.use')) return null
  if (pathname.startsWith('/learning/courses') && !hasPermission(user, 'learning.course.manage')) return null
  if (isExamAdminPath(pathname) && !hasPermission(user, 'learning.exam.manage')) return null

  return <LearningShell>{children}</LearningShell>
}
