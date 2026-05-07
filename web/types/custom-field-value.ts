export type CustomFieldFileAttachment = {
  url: string
  name: string
  size?: number
  content_type?: string | null
}

export type CustomFieldValue =
  | string
  | number
  | boolean
  | null
  | CustomFieldFileAttachment[]
