export const FieldDomain = {
  USER: 'user',
  ORGANIZATION: 'organization',
  SHARED_POOL: 'shared_pool',
} as const
export type FieldDomain = (typeof FieldDomain)[keyof typeof FieldDomain]

export const FieldType = {
  SINGLE_LINE_TEXT: 'single_line_text',
  MULTI_LINE_TEXT: 'multi_line_text',
  NUMBER: 'number',
  DATE: 'date',
  TIME: 'time',
  DATETIME: 'datetime',
  SINGLE_SELECT: 'single_select',
  MULTI_SELECT: 'multi_select',
  SINGLE_SELECT_TREE: 'single_select_tree',
  MULTI_SELECT_TREE: 'multi_select_tree',
  EMAIL: 'email',
  PHONE: 'phone',
  URL: 'url',
  FILE: 'file',
  RICH_TEXT: 'rich_text',
  USER_SELECT: 'user_select',
  ORGANIZATION_SELECT: 'organization_select',
  EMPLOYEE_SELECT: 'employee_select',
  GROUP_SELECT: 'group_select',
} as const
export type FieldType = (typeof FieldType)[keyof typeof FieldType]

export const FieldSource = {
  SYSTEM: 'system',
  CUSTOM: 'custom',
} as const
export type FieldSource = (typeof FieldSource)[keyof typeof FieldSource]

export const ApplicableModule = {
  TICKET: 'ticket',
  SESSION_SUMMARY: 'session_summary',
  CALL_SUMMARY: 'call_summary',
} as const
export type ApplicableModule = (typeof ApplicableModule)[keyof typeof ApplicableModule]

export const FieldDefaultState = {
  HIDDEN: 'hidden',
  REQUIRED: 'required',
  OPTIONAL: 'optional',
  READONLY: 'readonly',
} as const
export type FieldDefaultState = (typeof FieldDefaultState)[keyof typeof FieldDefaultState]

/**
 * Display labels for each FieldType — keyed by locale.
 * Used in field type selector dropdowns and table columns.
 */
export const FIELD_TYPE_LABELS: Record<FieldType, { zh: string; en: string }> = {
  [FieldType.SINGLE_LINE_TEXT]: { zh: '单行文本', en: 'Single Line Text' },
  [FieldType.MULTI_LINE_TEXT]: { zh: '多行文本', en: 'Multi Line Text' },
  [FieldType.NUMBER]: { zh: '数字', en: 'Number' },
  [FieldType.DATE]: { zh: '日期', en: 'Date' },
  [FieldType.TIME]: { zh: '时间', en: 'Time' },
  [FieldType.DATETIME]: { zh: '日期时间', en: 'Date & Time' },
  [FieldType.SINGLE_SELECT]: { zh: '单选', en: 'Single Select' },
  [FieldType.MULTI_SELECT]: { zh: '多选', en: 'Multi Select' },
  [FieldType.SINGLE_SELECT_TREE]: { zh: '树形单选', en: 'Tree Single Select' },
  [FieldType.MULTI_SELECT_TREE]: { zh: '树形多选', en: 'Tree Multi Select' },
  [FieldType.EMAIL]: { zh: '邮箱', en: 'Email' },
  [FieldType.PHONE]: { zh: '电话', en: 'Phone' },
  [FieldType.URL]: { zh: '链接', en: 'URL' },
  [FieldType.FILE]: { zh: '文件', en: 'File' },
  [FieldType.RICH_TEXT]: { zh: '富文本', en: 'Rich Text' },
  [FieldType.USER_SELECT]: { zh: '用户选择', en: 'User Select' },
  [FieldType.ORGANIZATION_SELECT]: { zh: '组织选择', en: 'Organization Select' },
  [FieldType.EMPLOYEE_SELECT]: { zh: '员工选择', en: 'Employee Select' },
  [FieldType.GROUP_SELECT]: { zh: '员工组选择', en: 'Group Select' },
}

export const FIELD_SOURCE_LABELS: Record<FieldSource, { zh: string; en: string }> = {
  [FieldSource.SYSTEM]: { zh: '系统', en: 'System' },
  [FieldSource.CUSTOM]: { zh: '自定义', en: 'Custom' },
}

export const APPLICABLE_MODULE_LABELS: Record<ApplicableModule, { zh: string; en: string }> = {
  [ApplicableModule.TICKET]: { zh: '工单', en: 'Ticket' },
  [ApplicableModule.SESSION_SUMMARY]: { zh: '会话纪要', en: 'Session Summary' },
  [ApplicableModule.CALL_SUMMARY]: { zh: '通话纪要', en: 'Call Summary' },
}

export const FIELD_DOMAIN_LABELS: Record<FieldDomain, { zh: string; en: string }> = {
  [FieldDomain.USER]: { zh: '用户', en: 'User' },
  [FieldDomain.ORGANIZATION]: { zh: '组织', en: 'Organization' },
  [FieldDomain.SHARED_POOL]: { zh: '共享字段池', en: 'Shared Pool' },
}

/**
 * Which FieldTypes use select-style options (flat list).
 */
export const SELECT_FIELD_TYPES: FieldType[] = [
  FieldType.SINGLE_SELECT,
  FieldType.MULTI_SELECT,
]

/**
 * Which FieldTypes use tree-style nodes.
 */
export const TREE_FIELD_TYPES: FieldType[] = [
  FieldType.SINGLE_SELECT_TREE,
  FieldType.MULTI_SELECT_TREE,
]
