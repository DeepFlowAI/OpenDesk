'use client'

import { IconPlus } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { ComponentCard } from './component-card'
import type { ComponentPreview, DashboardComponent } from '@/models/custom-dashboard'
import { clampComponent, resolveDashboardLayout } from '@/utils/custom-dashboard'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export function DashboardCanvas({
  components,
  previews,
  onChange,
  onAdd,
  onEdit,
  onCopy,
  onDelete,
}: {
  components: DashboardComponent[]
  previews: Record<string, ComponentPreview>
  onChange: (components: DashboardComponent[]) => void
  onAdd: () => void
  onEdit: (component: DashboardComponent) => void
  onCopy: (component: DashboardComponent) => void
  onDelete: (component: DashboardComponent) => void
}) {
  const { locale } = useLocaleStore()
  const maxRow = Math.max(16, ...components.map((item) => item.y + item.h + 2))

  function drop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault()
    const id = event.dataTransfer.getData('text/dashboard-component')
    const component = components.find((item) => item.id === id)
    if (!component) return
    const bounds = event.currentTarget.getBoundingClientRect()
    const x = Math.floor(((event.clientX - bounds.left) / bounds.width) * 12)
    const y = Math.max(0, Math.floor((event.clientY - bounds.top) / 32))
    const next = components.map((item) => item.id === id ? clampComponent({ ...item, x: x - Math.floor(item.w / 2), y }) : item)
    onChange(resolveDashboardLayout(next, id))
  }

  if (components.length === 0) {
    return <div className="flex min-h-96 items-center justify-center rounded-xl border border-dashed border-border bg-muted/30"><Button onClick={onAdd}><IconPlus />{t('cd.addFirstComponent', locale)}</Button></div>
  }

  return (
    <div
      className="grid grid-cols-12 auto-rows-[32px] gap-3 rounded-xl border border-border bg-muted/30 p-3"
      style={{ minHeight: maxRow * 32 }}
      onDragOver={(event) => event.preventDefault()}
      onDrop={drop}
    >
      {components.map((component) => (
        <ComponentCard
          key={component.id}
          component={component}
          preview={previews[component.id]}
          onEdit={() => onEdit(component)}
          onCopy={() => onCopy(component)}
          onDelete={() => onDelete(component)}
          onDragStart={(event) => { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/dashboard-component', component.id) }}
          onResize={(widthDelta, heightDelta) => {
            const next = components.map((item) => item.id === component.id ? clampComponent({ ...item, w: item.w + widthDelta, h: item.h + heightDelta }) : item)
            onChange(resolveDashboardLayout(next, component.id))
          }}
        />
      ))}
    </div>
  )
}
