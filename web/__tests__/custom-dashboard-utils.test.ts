import { describe, expect, it } from 'vitest'
import type { DashboardComponent } from '@/models/custom-dashboard'
import {
  clampComponent,
  componentsOverlap,
  findAvailablePosition,
  resolveDashboardLayout,
  validateComponent,
  validateDashboardForm,
} from '@/utils/custom-dashboard'

function component(id: string, x: number, y: number, w = 6, h = 8): DashboardComponent {
  return { id, title: id, code: 'def run():\n    return {"type": "metric", "value": 1}', x, y, w, h }
}

describe('custom dashboard layout', () => {
  it('clamps components to the twelve-column canvas', () => {
    expect(clampComponent(component('a', 11, -2, 6, 2))).toMatchObject({ x: 6, y: 0, w: 6, h: 4 })
  })

  it('pushes colliding components down while preserving the priority component', () => {
    const result = resolveDashboardLayout([component('a', 0, 0), component('b', 0, 0)], 'b')
    expect(result.find((item) => item.id === 'b')?.y).toBe(0)
    expect(result.find((item) => item.id === 'a')?.y).toBe(8)
    expect(componentsOverlap(result[0], result[1])).toBe(false)
  })

  it('finds the next non-overlapping position', () => {
    expect(findAvailablePosition([component('a', 0, 0)], 6, 8)).toEqual({ x: 6, y: 0 })
  })
})

describe('custom dashboard validation', () => {
  it('validates create form identifiers', () => {
    expect(validateDashboardForm({ name: 'Demo', slug: 'Bad-Slug', description: null, components: [] }, true)).toHaveProperty('slug')
    expect(validateDashboardForm({ name: 'Demo', slug: 'demo_1', description: null, components: [] }, true)).toEqual({})
  })

  it('requires a no-argument run function', () => {
    expect(validateComponent({ ...component('a', 0, 0), code: 'value = 1' })).toBe('run_required')
    expect(validateComponent(component('a', 0, 0))).toBeNull()
  })
})
