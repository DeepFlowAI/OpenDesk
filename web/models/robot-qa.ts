export type RobotQaSetting = {
  enabled: boolean
  knowledge_base_id: number | null
  knowledge_base_name: string | null
}

export type RobotQaSettingPayload = {
  enabled: boolean
  knowledge_base_id: number | null
}

export type RobotQaKnowledgeBase = {
  id: number
  name: string
  description: string | null
  status: string
}

export type RobotQaKnowledgeBaseList = {
  items: RobotQaKnowledgeBase[]
}

export type RobotQaRuntime = {
  enabled: boolean
  available: boolean
  knowledge_base_id: number | null
  knowledge_base_name: string | null
}

export type RobotQaDirectory = {
  id: number
  parent_id: number | null
  name: string
  sort_order: number
  depth: number
  path: string[]
}

export type RobotQaDirectoryList = {
  knowledge_base_id: number
  knowledge_base_name: string
  items: RobotQaDirectory[]
}

export type RobotQaCreatePayload = {
  directory_id: number
  question: string
  answer_markdown: string
  access_keywords: string[]
  enabled: boolean
}

export type RobotQaCreateResponse = {
  id: number
  knowledge_base_id: number
  directory_id: number
  process_status: string
}
