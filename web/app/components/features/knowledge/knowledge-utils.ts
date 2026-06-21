import type {
  KnowledgeDirectoryNode,
  KnowledgeDocument,
  KnowledgeDocumentDisplayStatus,
  KnowledgeValidityType,
} from '@/models/knowledge'
import { formatDatetimeForDisplay } from '@/lib/datetime-display'

export type FlatKnowledgeDirectory = {
  node: KnowledgeDirectoryNode
  depth: number
  path: string
}

export function flattenKnowledgeDirectories(
  nodes: KnowledgeDirectoryNode[],
  parentPath = '',
  depth = 1,
): FlatKnowledgeDirectory[] {
  return nodes.flatMap((node) => {
    const path = parentPath ? `${parentPath} / ${node.name}` : node.name
    return [
      { node, depth, path },
      ...flattenKnowledgeDirectories(node.children ?? [], path, depth + 1),
    ]
  })
}

export function findKnowledgeDirectory(
  nodes: KnowledgeDirectoryNode[],
  id: number | null | undefined,
): KnowledgeDirectoryNode | null {
  if (id == null) return null
  for (const node of nodes) {
    if (node.id === id) return node
    const child = findKnowledgeDirectory(node.children ?? [], id)
    if (child) return child
  }
  return null
}

export function isKnowledgeDirectoryDescendant(
  nodes: KnowledgeDirectoryNode[],
  parentId: number,
  maybeChildId: number,
): boolean {
  const parent = findKnowledgeDirectory(nodes, parentId)
  if (!parent) return false
  return findKnowledgeDirectory(parent.children ?? [], maybeChildId) != null
}

export function knowledgeRootTotal(nodes: KnowledgeDirectoryNode[]): number {
  return nodes.reduce((sum, node) => sum + node.document_count, 0)
}

export function knowledgeDirectoryPath(document: KnowledgeDocument): string {
  return document.directory_path.map((item) => item.name).join(' / ')
}

export function knowledgeActorName(document: KnowledgeDocument): string {
  return document.updated_by?.actor_name || document.created_by?.actor_name || '-'
}

export function formatKnowledgeDate(raw: string | null | undefined): string {
  if (!raw) return '-'
  return formatDatetimeForDisplay(raw)
}

export function formatKnowledgeValidity(
  validityType: KnowledgeValidityType,
  validFrom: string | null,
  validTo: string | null,
  isZh: boolean,
): string {
  if (validityType === 'permanent') return isZh ? '永久有效' : 'Permanent'
  if (!validFrom || !validTo) return isZh ? '未设置' : 'Unset'
  return `${formatKnowledgeDate(validFrom).slice(0, 16)} - ${formatKnowledgeDate(validTo).slice(0, 16)}`
}

export function knowledgeStatusLabel(status: KnowledgeDocumentDisplayStatus, isZh: boolean): string {
  if (status === 'published') return isZh ? '已发布' : 'Published'
  if (status === 'expired') return isZh ? '已过期' : 'Expired'
  return isZh ? '草稿' : 'Draft'
}

export function knowledgeStatusClass(status: KnowledgeDocumentDisplayStatus): string {
  if (status === 'published') return 'bg-[#ECFDF5] text-[#047857]'
  if (status === 'expired') return 'bg-[#FEF2F2] text-[#DC2626]'
  return 'bg-[#F3F4F6] text-[#404040]'
}

export function toDatetimeLocalValue(raw: string | null | undefined): string {
  if (!raw) return ''
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return raw.slice(0, 16)
  const p2 = (value: number) => String(value).padStart(2, '0')
  return (
    `${date.getFullYear()}-${p2(date.getMonth() + 1)}-${p2(date.getDate())}` +
    `T${p2(date.getHours())}:${p2(date.getMinutes())}`
  )
}

export function fromDatetimeLocalValue(value: string): string | null {
  return value.trim() ? value.trim() : null
}

export function stripKnowledgeHtml(html: string): string {
  return knowledgeHtmlToMessageText(html)
}

function decodeKnowledgeHtmlEntities(text: string): string {
  if (typeof window === 'undefined') return text
  const textarea = document.createElement('textarea')
  textarea.innerHTML = text
  return textarea.value
}

export function knowledgeHtmlToMessageText(html: string): string {
  const withBreaks = html
    .replace(/<\s*br\s*\/?\s*>/gi, '\n')
    .replace(/<\s*li[^>]*>/gi, '\n- ')
    .replace(/<\s*\/(p|div|h[1-6]|blockquote|pre|li|ul|ol|tr)\s*>/gi, '\n')
    .replace(/<\s*\/(td|th)\s*>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')

  return decodeKnowledgeHtmlEntities(withBreaks)
    .split('\n')
    .map((line) => line.replace(/[ \t]+/g, ' ').trim())
    .filter(Boolean)
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function knowledgeHasUnsupportedSendContent(html: string): boolean {
  return /<(img|picture|video|audio|table|iframe|object|embed|figure)\b/i.test(html)
}

export function buildKnowledgeReturnQuery(params: URLSearchParams): string {
  const keep = new URLSearchParams()
  for (const key of ['directory', 'q', 'page']) {
    const value = params.get(key)
    if (value) keep.set(key, value)
  }
  const qs = keep.toString()
  return qs ? `?${qs}` : ''
}

export function knowledgeListHref(params: URLSearchParams): string {
  return `/workspace/knowledge${buildKnowledgeReturnQuery(params)}`
}

export async function readKnowledgeError(error: unknown, fallback: string): Promise<string> {
  const maybeResponse = error as { response?: { json?: () => Promise<unknown> } }
  if (maybeResponse.response?.json) {
    try {
      const body = await maybeResponse.response.json()
      if (body && typeof body === 'object') {
        const record = body as Record<string, unknown>
        if (typeof record.message === 'string') return record.message
        if (typeof record.detail === 'string') return record.detail
      }
    } catch {
      return fallback
    }
  }
  return fallback
}
