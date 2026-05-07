/**
 * Shared filter condition shape — identical across user / organization /
 * ticket domains at both the view config and workspace layers.
 * Kept structurally compatible with `ConditionItem` in:
 *   - web/models/user-view.ts
 *   - web/models/organization-view.ts
 *   - web/models/ticket-view.ts
 */
export type FilterConditionItem = {
  field_id: number | null
  field_key: string | null
  operator: string
  value: string | number | boolean | null | unknown[]
}
