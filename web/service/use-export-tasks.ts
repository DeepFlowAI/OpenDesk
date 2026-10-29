'use client'

import { useEffect, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { HTTPError } from 'ky'
import { useAuthStore } from '@/context/auth-store'
import type { ExportStatus, ExportSubmission, ExportTask, ExportTaskList } from '@/models/export-task'
import { get, post } from './base'

export const exportKeys = ['export-tasks'] as const

export function useExportIdentity() {
  const user = useAuthStore((state) => state.user)
  return `${user?.tenant_id ?? ''}:${user?.id ?? ''}`
}

export function useExportForeground() {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const update = () => setVisible(document.visibilityState === 'visible')
    update()
    document.addEventListener('visibilitychange', update)
    return () => document.removeEventListener('visibilitychange', update)
  }, [])
  return visible
}

export function useExportStatus() {
  const identity = useExportIdentity()
  const token = useAuthStore((state) => state.token)
  const visible = useExportForeground()
  return useQuery({
    queryKey: [...exportKeys, identity, 'status'],
    queryFn: ({ signal }) => get<ExportStatus>('v1/exports/status', { signal }),
    enabled: Boolean(token) && visible,
    refetchInterval: visible ? 5000 : false,
    refetchOnWindowFocus: 'always',
    retry: false,
  })
}

export function useExportTasks(page: number, perPage: number) {
  const identity = useExportIdentity()
  const token = useAuthStore((state) => state.token)
  const visible = useExportForeground()
  return useQuery({
    queryKey: [...exportKeys, identity, 'list', page, perPage],
    queryFn: ({ signal }) => get<ExportTaskList>('v1/exports', {
      searchParams: { page, per_page: perPage }, signal,
    }),
    enabled: Boolean(token) && visible,
    placeholderData: (previous, previousQuery) => previousQuery?.queryKey[1] === identity
      ? keepPreviousData(previous) : undefined,
    refetchInterval: visible ? 5000 : false,
    refetchOnWindowFocus: 'always',
    retry: false,
  })
}

export async function exportErrorCode(error: unknown): Promise<string> {
  if (error instanceof HTTPError) {
    try {
      const body = await error.response.clone().json() as { code?: string }
      if (body.code?.startsWith('EXPORT_')) return body.code.slice(7).toLowerCase()
    } catch { /* Use a safe, translated fallback. */ }
  }
  return 'download_failed'
}

/** Keep the same submission key until this logical submission is resolved. */
export async function createExportTask(body: ExportSubmission): Promise<ExportTask> {
  try {
    return await post<ExportTask>('v1/exports', { json: body, retry: 0 })
  } catch (error) {
    if (error instanceof HTTPError && error.response.status < 500) throw error
    // An uncertain response must be reconciled before the caller attempts another submission.
    try {
      return await get<ExportTask>(`v1/exports/by-key/${body.idempotency_key}`, { retry: 0 })
    } catch {
      throw error
    }
  }
}

export const cancelExportTask = (id: string) => post<ExportTask>(`v1/exports/${id}/cancel`, { retry: 0 })
export const markExportsViewed = (ids: string[]) => post('v1/exports/viewed', { json: { ids } })
export const claimExportNotifications = (since: string, signal: AbortSignal) =>
  post<{ items: ExportTask[]; server_time: string }>('v1/exports/notifications', { json: { since }, signal, retry: 0 })
export const downloadExportTask = (id: string) => get<{ url: string }>(`v1/exports/${id}/download`, { timeout: 120000, retry: 0 })
