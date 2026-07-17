'use client'

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { IconLoader2, IconX } from '@tabler/icons-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { normalizeRobotQaKeyword, robotQaAnswerMarkdownFromMessage } from '@/lib/robot-qa-message-content'
import type { Message } from '@/models/conversation'
import type { RobotQaDirectory, RobotQaRuntime } from '@/models/robot-qa'
import { useCreateRobotQa, useRobotQaDirectories } from '@/service/use-robot-qa'

type RobotQaCreateDialogProps = {
  open: boolean
  message: Message
  runtime: RobotQaRuntime
  isZh: boolean
  onClose: () => void
}

type RobotQaApiError = {
  status?: number
  code?: string
}

export function defaultRobotQaDirectoryId(items: RobotQaDirectory[]): string {
  const uncategorized = items.find((item) => item.parent_id == null && item.name.trim() === '未分类')
  return String(uncategorized?.id ?? '')
}

export function filterRobotQaDirectories(items: RobotQaDirectory[], search: string): RobotQaDirectory[] {
  const keyword = search.trim().toLocaleLowerCase()
  if (!keyword) return items
  return items.filter((item) => `${item.path.join(' / ')} ${item.name}`.toLocaleLowerCase().includes(keyword))
}

export function robotQaDirectoryLabel(item: RobotQaDirectory): string {
  return item.path.length > 0 ? item.path.join(' / ') : item.name
}

async function readRobotQaApiError(error: unknown): Promise<RobotQaApiError> {
  const response = (error as { response?: Response }).response
  if (!response) return {}
  try {
    const body = await response.clone().json() as { code?: string }
    return { status: response.status, code: body.code }
  } catch {
    return { status: response.status }
  }
}

export function RobotQaCreateDialog({
  open,
  message,
  runtime,
  isZh,
  onClose,
}: RobotQaCreateDialogProps) {
  const directories = useRobotQaDirectories(open, runtime.knowledge_base_id)
  const createQa = useCreateRobotQa(message.conversation_id, message.id)
  const initialAnswer = useMemo(() => robotQaAnswerMarkdownFromMessage(message), [message])
  const defaultDirectoryId = useMemo(
    () => defaultRobotQaDirectoryId(directories.data?.items ?? []),
    [directories.data?.items],
  )

  const [directoryId, setDirectoryId] = useState('')
  const [directorySearch, setDirectorySearch] = useState('')
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(initialAnswer)
  const [keywords, setKeywords] = useState<string[]>([])
  const [keywordInput, setKeywordInput] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [questionError, setQuestionError] = useState('')
  const [answerError, setAnswerError] = useState('')
  const [keywordError, setKeywordError] = useState('')
  const questionRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    setDirectoryId(defaultDirectoryId)
  }, [defaultDirectoryId, open])

  useEffect(() => {
    if (!open) return
    setQuestion('')
    setDirectorySearch('')
    setAnswer(initialAnswer)
    setKeywords([])
    setKeywordInput('')
    setEnabled(true)
    setQuestionError('')
    setAnswerError('')
    setKeywordError('')
  }, [initialAnswer, message.id, open])

  const dirty = question.length > 0
    || answer !== initialAnswer
    || keywords.length > 0
    || keywordInput.trim().length > 0
    || !enabled
    || (directoryId.length > 0 && directoryId !== defaultDirectoryId)
  const filteredDirectories = useMemo(
    () => filterRobotQaDirectories(directories.data?.items ?? [], directorySearch),
    [directories.data?.items, directorySearch],
  )
  const directorySelectItems = useMemo(
    () => (directories.data?.items ?? []).map((item) => ({
      value: String(item.id),
      label: robotQaDirectoryLabel(item),
    })),
    [directories.data?.items],
  )

  const requestClose = () => {
    if (createQa.isPending) return
    if (dirty && !window.confirm(isZh ? '当前内容尚未提交，确定关闭吗？' : 'Discard the unsaved QA?')) return
    onClose()
  }

  const addKeyword = (rawValue: string): boolean => {
    const normalized = normalizeRobotQaKeyword(rawValue)
    if (!normalized) {
      setKeywordError(isZh ? '仅支持英文字母、数字和下划线' : 'Use only ASCII letters, numbers, and underscores')
      return false
    }
    if (keywords.includes(normalized)) {
      setKeywordInput('')
      setKeywordError('')
      return true
    }
    if (keywords.length >= 50) {
      setKeywordError(isZh ? '最多添加 50 个权限关键词' : 'Add up to 50 permission keywords')
      return false
    }
    setKeywords((current) => [...current, normalized])
    setKeywordInput('')
    setKeywordError('')
    return true
  }

  const handleKeywordKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter' && event.key !== ',') return
    event.preventDefault()
    if (keywordInput.trim()) addKeyword(keywordInput)
  }

  const handleSubmit = async () => {
    const normalizedQuestion = question.trim()
    const normalizedAnswer = answer.trim()
    if (!directoryId) return
    if (!normalizedQuestion) {
      setQuestionError(isZh ? '请输入问题' : 'Enter a question')
      questionRef.current?.focus()
      return
    }
    if (!normalizedAnswer) {
      setAnswerError(isZh ? '请输入答案' : 'Enter an answer')
      return
    }
    if (normalizedAnswer.length > 7000) {
      setAnswerError(isZh ? '答案最多 7000 个字符' : 'The answer may contain up to 7,000 characters')
      return
    }
    if (keywordInput.trim() && !addKeyword(keywordInput)) return

    const pendingKeyword = normalizeRobotQaKeyword(keywordInput)
    const submitKeywords = pendingKeyword && !keywords.includes(pendingKeyword)
      ? [...keywords, pendingKeyword]
      : keywords
    try {
      await createQa.mutateAsync({
        directory_id: Number(directoryId),
        question: normalizedQuestion,
        answer_markdown: normalizedAnswer,
        access_keywords: submitKeywords,
        enabled,
      })
      toast.success(isZh ? '已提交，系统正在处理' : 'Submitted. The system is processing the new QA.')
      onClose()
    } catch (error) {
      const apiError = await readRobotQaApiError(error)
      if (apiError.code === 'ROBOT_QA_QUESTION_DUPLICATE') {
        setQuestionError(isZh ? '目标知识库已存在相同问题' : 'The target knowledge base already contains the same question')
        questionRef.current?.focus()
        return
      }
      if (apiError.status === 403) {
        toast.error(isZh ? '无权限新建机器人 QA' : 'You do not have permission to create robot QA')
      } else if (apiError.code === 'ROBOT_QA_CONFIG_INVALID') {
        toast.error(isZh ? '机器人 QA 配置已失效，请联系管理员' : 'Robot QA configuration is no longer valid')
      } else {
        toast.error(isZh ? '新建失败，请稍后重试' : 'Failed to create robot QA. Try again later.')
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && requestClose()}>
      <DialogContent
        className="flex max-h-[calc(100vh-2rem)] max-w-[680px] flex-col gap-0 overflow-hidden p-0 sm:max-w-[680px]"
        showCloseButton={false}
      >
        <DialogHeader className="border-b border-border px-6 py-4">
          <DialogTitle>{isZh ? '新建机器人 QA' : 'Create robot QA'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-5 overflow-y-auto px-6 py-5">
          <div className="grid gap-2">
            <Label>{isZh ? '目标知识库' : 'Target knowledge base'}</Label>
            <Input value={runtime.knowledge_base_name ?? ''} disabled />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="robot-qa-directory">{isZh ? 'QA 目录' : 'QA directory'} *</Label>
            {directories.isLoading ? (
              <div className="h-9 animate-pulse rounded-lg bg-muted/50" />
            ) : directories.isError ? (
              <div className="flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                <span>{isZh ? '目录加载失败' : 'Failed to load directories'}</span>
                <Button variant="ghost" size="sm" onClick={() => void directories.refetch()}>
                  {isZh ? '重试' : 'Retry'}
                </Button>
              </div>
            ) : (directories.data?.items.length ?? 0) === 0 ? (
              <p className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-foreground">
                {isZh ? '目标知识库暂无 QA 目录，请先在 OpenAgent 创建目录' : 'This knowledge base has no QA directories. Create one in OpenAgent first.'}
              </p>
            ) : (
              <div className="space-y-2">
                <Input
                  type="search"
                  value={directorySearch}
                  disabled={createQa.isPending}
                  placeholder={isZh ? '搜索 QA 目录' : 'Search QA directories'}
                  onChange={(event) => setDirectorySearch(event.target.value)}
                />
                <Select
                  items={directorySelectItems}
                  value={directoryId}
                  onValueChange={(value) => setDirectoryId(value ?? '')}
                  disabled={directories.isLoading || createQa.isPending}
                >
                  <SelectTrigger id="robot-qa-directory" className="w-full">
                    <SelectValue placeholder={directories.isLoading ? (isZh ? '加载中…' : 'Loading…') : (isZh ? '请选择目录' : 'Select a directory')} />
                  </SelectTrigger>
                  <SelectContent>
                    {filteredDirectories.map((item) => (
                      <SelectItem key={item.id} value={String(item.id)}>
                        {robotQaDirectoryLabel(item)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="robot-qa-question">{isZh ? '问题' : 'Question'} *</Label>
              <span className="text-xs text-muted-foreground">{question.length}/500</span>
            </div>
            <Input
              ref={questionRef}
              id="robot-qa-question"
              value={question}
              maxLength={500}
              disabled={createQa.isPending}
              aria-invalid={Boolean(questionError)}
              onChange={(event) => {
                setQuestion(event.target.value)
                setQuestionError('')
              }}
            />
            {questionError && <p className="text-xs text-destructive">{questionError}</p>}
          </div>

          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="robot-qa-answer">{isZh ? '答案（Markdown）' : 'Answer (Markdown)'} *</Label>
              <span className="text-xs text-muted-foreground">{answer.length}/7000</span>
            </div>
            <Textarea
              id="robot-qa-answer"
              value={answer}
              maxLength={7000}
              rows={10}
              disabled={createQa.isPending}
              className="min-h-52 resize-y font-mono"
              aria-invalid={Boolean(answerError)}
              onChange={(event) => {
                setAnswer(event.target.value)
                setAnswerError('')
              }}
            />
            {answerError && <p className="text-xs text-destructive">{answerError}</p>}
          </div>

          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="robot-qa-keywords">{isZh ? '权限关键词' : 'Permission keywords'}</Label>
              <span className="text-xs text-muted-foreground">{keywords.length}/50</span>
            </div>
            {keywords.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {keywords.map((keyword) => (
                  <span key={keyword} className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-xs">
                    {keyword}
                    <button
                      type="button"
                      aria-label={isZh ? `删除 ${keyword}` : `Remove ${keyword}`}
                      disabled={createQa.isPending}
                      onClick={() => setKeywords((current) => current.filter((item) => item !== keyword))}
                    >
                      <IconX size={13} />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <Input
              id="robot-qa-keywords"
              value={keywordInput}
              disabled={createQa.isPending || keywords.length >= 50}
              placeholder={isZh ? '输入后按回车，支持字母、数字、下划线' : 'Type and press Enter; letters, numbers, underscores'}
              aria-invalid={Boolean(keywordError)}
              onChange={(event) => {
                setKeywordInput(event.target.value)
                setKeywordError('')
              }}
              onKeyDown={handleKeywordKeyDown}
              onBlur={() => keywordInput.trim() && addKeyword(keywordInput)}
            />
            {keywordError && <p className="text-xs text-destructive">{keywordError}</p>}
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-3">
            <div>
              <Label htmlFor="robot-qa-enabled">{isZh ? '启用 QA' : 'Enable QA'}</Label>
              <p className="mt-1 text-xs text-muted-foreground">
                {isZh ? '关闭后仍会创建，但不会参与机器人回答' : 'When off, the QA is created but not used in answers'}
              </p>
            </div>
            <Switch id="robot-qa-enabled" checked={enabled} onCheckedChange={setEnabled} disabled={createQa.isPending} />
          </div>
        </div>

        <DialogFooter className="px-6">
          <Button variant="outline" onClick={requestClose} disabled={createQa.isPending}>
            {isZh ? '取消' : 'Cancel'}
          </Button>
          <Button
            onClick={() => void handleSubmit()}
            disabled={createQa.isPending || directories.isLoading || directories.isError || !directoryId}
          >
            {createQa.isPending && <IconLoader2 className="animate-spin" />}
            {isZh ? '提交' : 'Submit'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
