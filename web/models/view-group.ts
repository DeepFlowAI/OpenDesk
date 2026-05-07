/**
 * Shared types for the view-group aggregation API used by ticket / user /
 * organization workspaces. The server contract lives at
 * `app/schemas/view_group.py`.
 */

/** Mirrors xxx-view.ConditionItem; kept domain-agnostic so all three domains
 *  can share the same view-group request shape. */
export type ViewGroupConditionItem = {
  field_id: number | null
  field_key: string | null
  operator: string
  value: string | number | boolean | null | unknown[]
}

export type ViewGroupRequestPayload = {
  search?: string | null
  temp_conditions?: ViewGroupConditionItem[]
  temp_condition_logic?: 'and' | 'or'
}

export type ViewGroupItem = {
  value: string | null
  count: number
}

export type ViewGroupFieldInfo = {
  id: number
  field_type: string
  name: string
}

export type ViewGroupResponse = {
  group_field: ViewGroupFieldInfo | null
  items: ViewGroupItem[]
  total: number
}
