'use client'

import { WorkspaceColumnsDrawer } from '@/components/workspace/columns-drawer'
import type { ColumnConfigItem } from '@/models/organization-view'
import type { UnifiedField } from '@/models/field-definition'

type Props = {
  locale: string
  fields: UnifiedField[]
  baselineConfig: ColumnConfigItem[] | null
  currentOverride: ColumnConfigItem[] | null
  onApply: (cols: ColumnConfigItem[]) => void
  onReset: () => void
  onClose: () => void
}

export function ColumnsDrawer(props: Props) {
  return <WorkspaceColumnsDrawer {...props} />
}
