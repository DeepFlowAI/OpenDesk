'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconAlertCircle, IconArrowLeft, IconCheck, IconCopy, IconEye, IconGripVertical, IconInfoCircle, IconLoader2, IconPlus, IconRefresh, IconTrash, IconUpload } from '@tabler/icons-react'
import { arrayMove } from '@dnd-kit/sortable'
import CodeMirror, { type ReactCodeMirrorProps } from '@uiw/react-codemirror'
import { javascript } from '@codemirror/lang-javascript'
import { json } from '@codemirror/lang-json'
import { okaidiaInit } from '@uiw/codemirror-theme-okaidia'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { AssistPanelConfigValue, ChannelConfig, ChannelCustomButton, CreateChannelPayload } from '@/models/channel'
import { useChannel, useCreateChannel, useUpdateChannel } from '@/service/use-channels'
import { useOpenAgentAgents, useOpenAgentSettings } from '@/service/use-open-agent-settings'
import { useServiceHours } from '@/service/use-service-hours'
import { useUploadChannelLogo, useUploadChannelFavicon, useUploadChannelBotAvatar } from '@/service/use-upload'
import { CHANNEL_COLOR_PREVIEW, channelColorPreview } from '@/utils/channel-config-display'
import { ChannelColorField } from '@/components/channel/channel-color-field'
import { Switch } from '@/components/ui/switch'
import { SortableFieldRowsContext, SortableFieldTableRow } from '@/components/admin/sortable-field-table'
import { RichTextFieldEditor } from '@/app/components/features/field-system/rich-text-field-editor'
import {
  AssistPanelRuntime,
  createAssistPanelError,
  createAssistPanelOk,
  getAssistPanelCodeError,
  type AssistPanelApi,
  type AssistPanelEventName,
  type AssistPanelStatus,
} from '@/app/components/features/visitor-chat/assist-panel-runtime'

const DEFAULT_OFFLINE_TITLE = '当前客服不在线'
const DEFAULT_OFFLINE_MESSAGE = '您好，当前客服不在线，您可以稍后再来咨询，我们会尽快为您服务。'
const DEFAULT_LEAVE_MESSAGE_PROMPT = '请留下您的问题和联系方式，我们上线后会尽快联系您。'
const DEFAULT_QUEUE_MESSAGE = '您已进入人工客服队列。当前排队人数：{{current_queue_count}} 位，请稍候。客服接入后会立即回复您。'
const DEFAULT_QUEUE_FULL_MESSAGE = '当前排队人数较多，暂时无法进入排队。您可以稍后再试，或点击留言，我们上线后会尽快联系您。'
const DEFAULT_QUEUE_FULL_LEAVE_MESSAGE_BUTTON_LABEL = '留言'
const QUEUE_COUNT_VARIABLE = '{{current_queue_count}}'
const DEFAULT_OPEN_AGENT_INPUT_PLACEHOLDER = '输入消息...'
const DEFAULT_OPEN_AGENT_HANDOFF_LABEL = '转人工'
const MAX_CUSTOM_BUTTONS = 8
const DEFAULT_ASSIST_PANEL_CODE = `export default function AssistApp({ api, status, config }) {
  const items = Array.isArray(config.items) ? config.items : []
  const description = typeof config.description === 'string' ? config.description : ''

  return React.createElement(
    'div',
    { className: 'flex flex-col gap-3 text-sm' },
    description
      ? React.createElement('p', { className: 'leading-6 text-muted-foreground' }, description)
      : null,
    ...items.map((item, index) => {
      const record = item && typeof item === 'object' ? item : {}
      const question = record.question || record.title || ''
      const answer = record.answer || record.description || ''
      const message = record.message || question
      return React.createElement(
        'div',
        { key: index, className: 'rounded-lg border border-border bg-background p-3' },
        question ? React.createElement('p', { className: 'font-medium text-foreground' }, question) : null,
        answer ? React.createElement('p', { className: 'mt-1 text-xs leading-5 text-muted-foreground' }, answer) : null,
        message
          ? React.createElement(
              'button',
              {
                type: 'button',
                disabled: !status.canSendMessage,
                onClick: () => api.sendMessage(message),
                className: 'mt-3 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-40',
              },
              status.canSendMessage ? '发送到会话' : '当前不可发送',
            )
          : null,
      )
    }),
  )
}`
const DEFAULT_ASSIST_PANEL_CONFIG: Record<string, AssistPanelConfigValue> = {
  description: '这里展示 PC 独立 URL 访客侧辅助信息。',
  items: [
    {
      question: '常见问题',
      answer: '可以在初始参数 JSON 中配置问题、说明和要发送到会话的文本。',
      message: '我想了解常见问题',
    },
  ],
}

const DEFAULT_CONFIG: ChannelConfig = {
  title: null,
  document_title: null,
  page_bg_color: null,
  header_gradient_start: null,
  header_gradient_end: null,
  header_title_color: '#FFFFFF',
  message_area_bg_color: null,
  agent_bubble_bg_color: null,
  agent_bubble_text_color: null,
  agent_bubble_border_color: null,
  agent_bubble_radius: [10, 10, 10, 10],
  use_agent_avatar: false,
  user_bubble_bg_color: null,
  user_bubble_text_color: null,
  user_bubble_border_color: null,
  user_bubble_radius: [10, 10, 10, 10],
  embed_button_bg_color: null,
  embed_button_icon_color: null,
  send_button_bg_color: null,
  input_placeholder: null,
  service_hours_enabled: false,
  service_hours_id: null,
  outside_service_hours_strategy: 'offline_message',
  offline_title: DEFAULT_OFFLINE_TITLE,
  offline_message: DEFAULT_OFFLINE_MESSAGE,
  leave_message_prompt: DEFAULT_LEAVE_MESSAGE_PROMPT,
  queue_message: DEFAULT_QUEUE_MESSAGE,
  queue_full_message: DEFAULT_QUEUE_FULL_MESSAGE,
  queue_full_show_leave_message_button: true,
  queue_full_leave_message_button_label: DEFAULT_QUEUE_FULL_LEAVE_MESSAGE_BUTTON_LABEL,
  open_agent_enabled: false,
  open_agent_agent_id: null,
  open_agent_agent_name: null,
  open_agent_bot_strategy: 'always',
  open_agent_bot_service_hours_id: null,
  open_agent_avatar_url: null,
  open_agent_input_placeholder: null,
  open_agent_handoff_enabled: true,
  open_agent_handoff_label: DEFAULT_OPEN_AGENT_HANDOFF_LABEL,
  open_agent_handoff_after_messages: 2,
  open_agent_handoff_behavior: 'confirm',
  open_agent_custom_buttons_enabled: false,
  open_agent_custom_buttons: [],
  human_custom_buttons_enabled: false,
  human_custom_buttons: [],
  assist_panel_enabled: false,
  assist_panel_title: null,
  assist_panel_react_code: null,
  assist_panel_config: {},
}

/* ── Primitives ── */

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="text-base font-semibold text-foreground">{children}</h3>
}

function SubSectionTitle({ children }: { children: React.ReactNode }) {
  return <p className="text-sm font-semibold text-muted-foreground">{children}</p>
}

function Separator() {
  return <div className="h-px w-full bg-border" />
}

function FieldLabel({ label, required }: { label: string; required?: boolean }) {
  return (
    <div className="flex items-center gap-0.5">
      <span className="text-sm font-medium text-foreground">{label}</span>
      {required && <span className="text-sm font-medium text-destructive">*</span>}
    </div>
  )
}

function TextInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="h-10 w-full rounded-lg border border-border bg-white px-3.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
    />
  )
}

function createCustomButton(): ChannelCustomButton {
  return {
    label: '',
    action_type: 'send_message',
    message: '',
    url: null,
    enabled: true,
  }
}

function normalizeCustomButton(button: ChannelCustomButton): ChannelCustomButton {
  const label = button.label.trim()
  if (button.action_type === 'link') {
    return {
      label,
      action_type: 'link',
      message: null,
      url: button.url?.trim() || null,
      enabled: true,
    }
  }
  return {
    label,
    action_type: 'send_message',
    message: button.message?.trim() || null,
    url: null,
    enabled: true,
  }
}

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

function validateCustomButtonGroup(buttons: ChannelCustomButton[], locale: 'zh' | 'en'): string | null {
  if (buttons.length > MAX_CUSTOM_BUTTONS) return t('ch.form.customButtons.maxCount', locale)
  for (let i = 0; i < buttons.length; i += 1) {
    const button = normalizeCustomButton(buttons[i])
    const index = i + 1
    if (!button.label) return t('ch.form.customButtons.error.labelRequired', locale, { index })
    if (button.label.length > 16) return t('ch.form.customButtons.error.labelMax', locale, { index })
    if (button.action_type === 'send_message') {
      if (!button.message) return t('ch.form.customButtons.error.messageRequired', locale, { index })
      if (button.message.length > 500) return t('ch.form.customButtons.error.messageMax', locale, { index })
    } else {
      if (!button.url) return t('ch.form.customButtons.error.urlRequired', locale, { index })
      if (button.url.length > 512) return t('ch.form.customButtons.error.urlMax', locale, { index })
      if (!isHttpUrl(button.url)) return t('ch.form.customButtons.error.urlInvalid', locale, { index })
    }
  }
  return null
}

function normalizeCustomButtonGroup(buttons: ChannelCustomButton[]): ChannelCustomButton[] {
  return buttons.map(normalizeCustomButton)
}

function CustomButtonGroupEditor({
  title,
  hint,
  enabled,
  buttons,
  error,
  onEnabledChange,
  onButtonsChange,
  onErrorClear,
}: {
  title: string
  hint: string
  enabled: boolean
  buttons: ChannelCustomButton[]
  error: string
  onEnabledChange: (enabled: boolean) => void
  onButtonsChange: (buttons: ChannelCustomButton[]) => void
  onErrorClear: () => void
}) {
  const { locale } = useLocaleStore()
  const visibleEditor = enabled || buttons.length > 0
  const buttonIds = useMemo(() => buttons.map((_, index) => `custom-button-${index}`), [buttons.length])

  const updateButton = (index: number, patch: Partial<ChannelCustomButton>) => {
    onButtonsChange(buttons.map((button, i) => (i === index ? { ...button, ...patch } : button)))
    onErrorClear()
  }

  const reorderButtons = (fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex) return
    onButtonsChange(arrayMove(buttons, fromIndex, toIndex))
    onErrorClear()
  }

  const deleteButton = (index: number) => {
    const button = buttons[index]
    const typeLabel = button.action_type === 'link'
      ? t('ch.form.customButtons.type.link', locale)
      : t('ch.form.customButtons.type.sendMessage', locale)
    const ok = window.confirm(
      `${t('ch.form.customButtons.delete.title', locale)}\n${t('ch.form.customButtons.delete.body', locale)}\n${button.label || '-'}\n${typeLabel}`,
    )
    if (!ok) return
    onButtonsChange(buttons.filter((_, i) => i !== index))
    onErrorClear()
  }

  return (
    <div className="rounded-lg border border-border bg-white p-4">
      <div className="flex items-start justify-between gap-6">
        <div className="flex flex-col gap-1">
          <FieldLabel label={title} />
          <p className="text-xs leading-5 text-muted-foreground">{hint}</p>
        </div>
        <Switch
          checked={enabled}
          onCheckedChange={(v) => {
            onEnabledChange(v)
            onErrorClear()
          }}
        />
      </div>

      {visibleEditor && (
        <div className="mt-4 flex flex-col gap-3">
          {buttons.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border bg-muted/30 px-4 py-5 text-center text-xs text-muted-foreground">
              {t('ch.form.customButtons.empty', locale)}
            </div>
          ) : (
            <div className="overflow-hidden rounded-lg border border-border bg-background">
              <div className="grid h-9 grid-cols-[36px_minmax(120px,1fr)_108px_minmax(180px,1.35fr)_40px] items-center gap-3 border-b border-border bg-muted/30 px-3 text-xs font-medium text-muted-foreground">
                <span />
                <span>{t('ch.form.customButtons.label', locale)} <span className="text-destructive">*</span></span>
                <span>{t('ch.form.customButtons.type', locale)} <span className="text-destructive">*</span></span>
                <span>{t('ch.form.customButtons.message', locale)} <span className="text-destructive">*</span></span>
                <span />
              </div>
              <SortableFieldRowsContext itemIds={buttonIds} onReorderIndices={reorderButtons}>
                {buttons.map((button, index) => {
                  const id = buttonIds[index]
                  const isLink = button.action_type === 'link'
                  return (
                    <SortableFieldTableRow
                      key={id}
                      id={id}
                      className="grid grid-cols-[36px_minmax(120px,1fr)_108px_minmax(180px,1.35fr)_40px] items-center gap-3 border-b border-border px-3 py-3 last:border-b-0"
                      dragCell={({ attributes, listeners }) => (
                        <div className="flex h-10 items-center">
                          <span
                            className="inline-flex cursor-grab touch-none select-none text-muted-foreground hover:text-foreground active:cursor-grabbing"
                            {...attributes}
                            {...listeners}
                          >
                            <IconGripVertical size={16} />
                          </span>
                        </div>
                      )}
                    >
                      <TextInput
                        value={button.label}
                        onChange={(v) => updateButton(index, { label: v })}
                        placeholder={t('ch.form.customButtons.label.placeholder', locale)}
                      />
                      <select
                        value={button.action_type}
                        onChange={(e) => updateButton(index, {
                          action_type: e.target.value === 'link' ? 'link' : 'send_message',
                        })}
                        className="h-10 w-full rounded-lg border border-border bg-white px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                      >
                        <option value="send_message">{t('ch.form.customButtons.type.sendMessage', locale)}</option>
                        <option value="link">{t('ch.form.customButtons.type.link', locale)}</option>
                      </select>
                      <TextInput
                        value={isLink ? button.url ?? '' : button.message ?? ''}
                        onChange={(v) => updateButton(index, isLink ? { url: v } : { message: v })}
                        placeholder={isLink ? 'https://example.com' : t('ch.form.customButtons.message.placeholder', locale)}
                      />
                      <div className="flex h-10 items-center justify-end">
                        <button
                          type="button"
                          onClick={() => deleteButton(index)}
                          className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
                          title={t('ch.form.customButtons.delete.action', locale)}
                        >
                          <IconTrash size={15} />
                        </button>
                      </div>
                    </SortableFieldTableRow>
                  )
                })}
              </SortableFieldRowsContext>
            </div>
          )}

          <button
            type="button"
            onClick={() => {
              if (buttons.length >= MAX_CUSTOM_BUTTONS) return
              onButtonsChange([...buttons, createCustomButton()])
              onErrorClear()
            }}
            disabled={buttons.length >= MAX_CUSTOM_BUTTONS}
            className="inline-flex h-9 w-fit items-center gap-1.5 rounded-lg border border-border px-3 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
          >
            <IconPlus size={15} />
            {buttons.length >= MAX_CUSTOM_BUTTONS
              ? t('ch.form.customButtons.maxCount', locale)
              : t('ch.form.customButtons.add', locale)}
          </button>
        </div>
      )}
      {error && <p className="mt-3 text-xs text-destructive">{error}</p>}
    </div>
  )
}

const ASSIST_PANEL_CODE_BASIC_SETUP: ReactCodeMirrorProps['basicSetup'] = {
  lineNumbers: true,
  highlightActiveLineGutter: true,
  foldGutter: true,
  dropCursor: true,
  allowMultipleSelections: true,
  indentOnInput: true,
  bracketMatching: true,
  closeBrackets: true,
  autocompletion: true,
  rectangularSelection: true,
  crosshairCursor: true,
  highlightActiveLine: true,
  highlightSelectionMatches: true,
  searchKeymap: true,
  foldKeymap: true,
  completionKeymap: true,
  lintKeymap: true,
  tabSize: 2,
}
const ASSIST_PANEL_REACT_CODE_EXTENSIONS: ReactCodeMirrorProps['extensions'] = [javascript({ jsx: true })]
const ASSIST_PANEL_JSON_CODE_EXTENSIONS: ReactCodeMirrorProps['extensions'] = [json()]
const ASSIST_PANEL_CODE_THEME = okaidiaInit({
  settings: {
    background: '#0A0A0A',
    gutterBackground: '#0A0A0A',
    gutterForeground: '#71717A',
    gutterBorder: '#27272A',
    foreground: '#E5E7EB',
    caret: '#FAFAFA',
    selection: '#2563EB55',
    selectionMatch: '#2563EB33',
    lineHighlight: '#18181B',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
  },
})

function SourceCodeEditor({
  value,
  onChange,
  placeholder,
  extensions,
  height,
  hasError,
}: {
  value: string
  onChange: (value: string) => void
  placeholder: string
  extensions: ReactCodeMirrorProps['extensions']
  height: string
  hasError?: boolean
}) {
  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      height={height}
      basicSetup={ASSIST_PANEL_CODE_BASIC_SETUP}
      extensions={extensions}
      theme={ASSIST_PANEL_CODE_THEME}
      indentWithTab
      className={`overflow-hidden rounded-lg border bg-[#0A0A0A] text-[13px] shadow-sm ${
        hasError ? 'border-destructive' : 'border-border'
      } [&_.cm-editor]:outline-none [&_.cm-focused]:outline-none [&_.cm-scroller]:font-mono [&_.cm-scroller]:leading-5`}
    />
  )
}

function stripHtml(value: string): string {
  return value.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim()
}

function formatAssistPanelConfig(value: Record<string, AssistPanelConfigValue> | null | undefined): string {
  return JSON.stringify(value && typeof value === 'object' ? value : {}, null, 2)
}

function isAssistPanelConfig(value: unknown): value is Record<string, AssistPanelConfigValue> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseAssistPanelConfig(text: string): { ok: true; value: Record<string, AssistPanelConfigValue> } | { ok: false } {
  const source = text.trim() || '{}'
  try {
    const parsed = JSON.parse(source) as unknown
    if (!isAssistPanelConfig(parsed)) return { ok: false }
    return { ok: true, value: parsed }
  } catch {
    return { ok: false }
  }
}

function validateAssistPanelCode(code: string): boolean {
  return getAssistPanelCodeError(code) === null
}

const ASSIST_PANEL_PREVIEW_STATUS: AssistPanelStatus = {
  stage: 'bot',
  conversationStatus: 'bot',
  connectionStatus: 'connected',
  botRunning: false,
  handoffRouting: false,
  canSendMessage: true,
  canRequestHumanHandoff: true,
  currentAgent: null,
}

function createAssistPanelPreviewApi(status: AssistPanelStatus): AssistPanelApi {
  return {
    getChannel: () => ({
      channel_key: 'preview',
      name: 'Web SDK',
      logo_url: null,
      config: { assist_panel_enabled: true },
    }),
    getConversation: () => ({
      public_id: 'preview',
      status: status.conversationStatus,
      ended: false,
      canSendMessage: status.canSendMessage,
    }),
    getCurrentStatus: () => status,
    subscribeStatus: (listener) => {
      listener(status)
      return () => undefined
    },
    subscribeEvent: (eventName: AssistPanelEventName, listener: (payload: unknown) => void) => {
      if (eventName === 'status_changed') listener(status)
      if (eventName === 'agent_changed') listener(status.currentAgent)
      if (eventName === 'conversation_changed') {
        listener({ public_id: 'preview', status: status.conversationStatus, ended: false })
      }
      if (eventName === 'message_created') listener(null)
      if (eventName === 'context_changed') listener(null)
      if (eventName === 'panel_visibility_changed') listener({ visible: true, collapsed: false })
      return () => undefined
    },
    getCurrentAgent: () => status.currentAgent,
    getVisitor: () => ({ external_id: 'preview' }),
    getMessages: () => [],
    sendMessage: async (text) => (
      typeof text === 'string' && text.trim()
        ? createAssistPanelOk()
        : createAssistPanelError('INVALID_PAYLOAD', 'Message text is invalid')
    ),
    setComposerText: (text) => (
      typeof text === 'string' && text.trim()
        ? createAssistPanelOk()
        : createAssistPanelError('INVALID_PAYLOAD', 'Composer text is invalid')
    ),
    requestHumanHandoff: async () => createAssistPanelOk(),
    openUrl: (url) => (
      typeof url === 'string' && (url.startsWith('/') || url.startsWith('https://'))
        ? createAssistPanelOk()
        : createAssistPanelError('INVALID_PAYLOAD', 'URL is invalid')
    ),
  }
}

function AssistPanelCodePreview({
  title,
  code,
  config,
}: {
  title: string
  code: string
  config: Record<string, AssistPanelConfigValue>
}) {
  const { locale } = useLocaleStore()
  const api = useMemo(() => createAssistPanelPreviewApi(ASSIST_PANEL_PREVIEW_STATUS), [])

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="truncate text-sm font-semibold text-foreground">{title}</p>
        <span className="shrink-0 rounded-full bg-muted px-2 py-1 text-[11px] text-muted-foreground">
          {locale === 'zh' ? '模拟预览' : 'Preview'}
        </span>
      </div>
      <AssistPanelRuntime
        code={code}
        api={api}
        status={ASSIST_PANEL_PREVIEW_STATUS}
        config={config}
        locale={locale}
      />
    </div>
  )
}

function RadiusField({ label, value, onChange }: { label: string; value: [number, number, number, number]; onChange: (v: [number, number, number, number]) => void }) {
  const { locale } = useLocaleStore()
  const labels = [
    t('ch.form.radius.tl', locale),
    t('ch.form.radius.tr', locale),
    t('ch.form.radius.bl', locale),
    t('ch.form.radius.br', locale),
  ]
  const updateAt = (i: number, raw: string) => {
    const next = [...value] as [number, number, number, number]
    next[i] = Math.max(0, Number(raw) || 0)
    onChange(next)
  }
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[13px] font-medium text-foreground">{label}</span>
      <div className="flex flex-col gap-2">
        {/* Row 1: TL + TR */}
        <div className="flex gap-3">
          {[0, 1].map((i) => (
            <div key={i} className="flex flex-col gap-1">
              <span className="text-[11px] text-muted-foreground">{labels[i]}</span>
              <input
                type="number"
                min={0}
                value={value[i]}
                onChange={(e) => updateAt(i, e.target.value)}
                className="h-7 w-16 rounded-md border border-border bg-white px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
          ))}
        </div>
        {/* Row 2: BL + BR */}
        <div className="flex gap-3">
          {[2, 3].map((i) => (
            <div key={i} className="flex flex-col gap-1">
              <span className="text-[11px] text-muted-foreground">{labels[i]}</span>
              <input
                type="number"
                min={0}
                value={value[i]}
                onChange={(e) => updateAt(i, e.target.value)}
                className="h-7 w-16 rounded-md border border-border bg-white px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

const MAX_LOGO_BYTES = 2 * 1024 * 1024
const MAX_FAVICON_BYTES = 512 * 1024
const MAX_BOT_AVATAR_BYTES = 5 * 1024 * 1024

/* ── Segmented control ── */

function SegmentedControl<V extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: V; label: string }[]
  value: V
  onChange: (v: V) => void
}) {
  return (
    <div className="flex gap-2">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`rounded-lg px-5 py-2.5 text-sm font-medium transition-colors ${
            value === opt.value
              ? 'bg-primary text-white'
              : 'border border-border text-muted-foreground hover:border-border hover:text-foreground/80'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

function StandardTabSwitch<V extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: V; label: string }[]
  value: V
  onChange: (v: V) => void
}) {
  return (
    <div className="inline-flex h-10 items-center rounded-lg border border-border bg-white p-1 shadow-sm">
      {options.map((opt) => {
        const active = value === opt.value
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.value)}
            className={`flex h-full items-center justify-center rounded-md px-5 text-sm font-medium transition-colors ${
              active
                ? 'bg-[#1F1F1F] text-white'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}

/* ── Copyable block ── */

function CopyBlock({
  content,
  copyLabel,
  copiedLabel,
  hint,
  multiline,
}: {
  content: string
  copyLabel: string
  copiedLabel: string
  hint: string
  multiline?: boolean
}) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* noop */ }
  }

  return (
    <>
      <div className="flex items-start gap-3">
        {multiline ? (
          <pre className="min-w-0 flex-1 overflow-x-auto whitespace-pre-wrap rounded-lg bg-accent px-3.5 py-2.5 font-mono text-[13px] text-foreground/80">
            {content}
          </pre>
        ) : (
          <code className="min-w-0 flex-1 truncate rounded-lg bg-accent px-3.5 py-2.5 font-mono text-[13px] text-foreground/80">
            {content}
          </code>
        )}
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border px-4 py-2 text-[13px] font-medium text-foreground/80 transition-colors hover:bg-accent"
        >
          {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
          {copied ? copiedLabel : copyLabel}
        </button>
      </div>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </>
  )
}

/* ── Access info sections ── */

function AccessLinkSection({ url }: { url: string }) {
  const { locale } = useLocaleStore()
  return (
    <div className="flex flex-col gap-3">
      <SubSectionTitle>{t('ch.section.accessLink', locale)}</SubSectionTitle>
      <CopyBlock
        content={url}
        copyLabel={t('ch.accessLink.copy', locale)}
        copiedLabel={t('ch.accessLink.copied', locale)}
        hint={t('ch.accessLink.hint', locale)}
      />
    </div>
  )
}

function EmbedCodeSection({ channelKey }: { channelKey: string }) {
  const { locale } = useLocaleStore()
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || `${origin}/api/`
  const snippet = `<script src="${origin}/sdk/opendesk.js"></script>\n<script>\n  OpenDesk.init({\n    channelKey: ${JSON.stringify(channelKey)},\n    apiBaseUrl: ${JSON.stringify(apiBaseUrl)},\n  });\n</script>`

  return (
    <div className="flex flex-col gap-3">
      <SubSectionTitle>{t('ch.section.embedCode', locale)}</SubSectionTitle>
      <CopyBlock
        content={snippet}
        copyLabel={t('ch.embedCode.copy', locale)}
        copiedLabel={t('ch.embedCode.copied', locale)}
        hint={t('ch.embedCode.hint', locale)}
        multiline
      />
    </div>
  )
}

/* ── Main form ── */

type ChannelFormProps = { channelId?: number }

export function ChannelForm({ channelId }: ChannelFormProps) {
  const isNew = channelId == null
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data: channel, isLoading } = useChannel(channelId ?? 0)
  const { data: serviceHours = [], isLoading: serviceHoursLoading } = useServiceHours()
  const { data: openAgentSettings, isLoading: openAgentSettingsLoading } = useOpenAgentSettings()
  const createMut = useCreateChannel()
  const updateMut = useUpdateChannel()
  const logoUploadMut = useUploadChannelLogo()
  const faviconUploadMut = useUploadChannelFavicon()
  const botAvatarUploadMut = useUploadChannelBotAvatar()
  const logoFileRef = useRef<HTMLInputElement>(null)
  const faviconFileRef = useRef<HTMLInputElement>(null)
  const botAvatarFileRef = useRef<HTMLInputElement>(null)

  const [name, setName] = useState('')
  const [accessMode, setAccessMode] = useState<'url' | 'embed'>('url')
  const [logoUrl, setLogoUrl] = useState('')
  const [logoError, setLogoError] = useState('')
  const [faviconUrl, setFaviconUrl] = useState('')
  const [faviconError, setFaviconError] = useState('')
  const [botAvatarError, setBotAvatarError] = useState('')
  const [config, setConfig] = useState<ChannelConfig>({ ...DEFAULT_CONFIG })
  const [initialized, setInitialized] = useState(false)
  const [savedId, setSavedId] = useState<number | null>(channelId ?? null)
  const [savedChannelKey, setSavedChannelKey] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'interface' | 'service' | 'assist'>('interface')
  const [serviceConfigError, setServiceConfigError] = useState('')
  const [openAgentConfigError, setOpenAgentConfigError] = useState('')
  const [openAgentAgentError, setOpenAgentAgentError] = useState('')
  const [openAgentBotServiceHoursError, setOpenAgentBotServiceHoursError] = useState('')
  const [openAgentInputPlaceholderError, setOpenAgentInputPlaceholderError] = useState('')
  const [openAgentHandoffLabelError, setOpenAgentHandoffLabelError] = useState('')
  const [openAgentHandoffThresholdError, setOpenAgentHandoffThresholdError] = useState('')
  const [openAgentCustomButtonsError, setOpenAgentCustomButtonsError] = useState('')
  const [humanCustomButtonsError, setHumanCustomButtonsError] = useState('')
  const [offlineTitleError, setOfflineTitleError] = useState('')
  const [offlineMessageError, setOfflineMessageError] = useState('')
  const [leaveMessagePromptError, setLeaveMessagePromptError] = useState('')
  const [queueMessageError, setQueueMessageError] = useState('')
  const [queueFullMessageError, setQueueFullMessageError] = useState('')
  const [queueFullButtonLabelError, setQueueFullButtonLabelError] = useState('')
  const [assistPanelTitleError, setAssistPanelTitleError] = useState('')
  const [assistPanelCodeError, setAssistPanelCodeError] = useState('')
  const [assistPanelConfigText, setAssistPanelConfigText] = useState(formatAssistPanelConfig({}))
  const [assistPanelConfigError, setAssistPanelConfigError] = useState('')
  const [assistPanelPreviewConfig, setAssistPanelPreviewConfig] = useState<Record<string, AssistPanelConfigValue>>({})
  const [assistPanelPreviewStatus, setAssistPanelPreviewStatus] = useState('')

  const openAgentConfigured = Boolean(openAgentSettings?.base_url && openAgentSettings?.has_api_key)
  const {
    data: openAgentAgents,
    isFetching: openAgentAgentsFetching,
    isError: openAgentAgentsIsError,
    refetch: refetchOpenAgentAgents,
  } = useOpenAgentAgents(activeTab === 'service' && config.open_agent_enabled && openAgentConfigured)
  const openAgentAgentItems = openAgentAgents?.items ?? []
  const selectedOpenAgent = openAgentAgentItems.find((item) => item.id === config.open_agent_agent_id)

  useEffect(() => {
    if (isNew) { if (!initialized) setInitialized(true); return }
    if (!channel || initialized) return
    setName(channel.name)
    setAccessMode(channel.access_mode === 'embed' ? 'embed' : 'url')
    setLogoUrl(channel.logo_url ?? '')
    setFaviconUrl(channel.favicon_url ?? '')
    setConfig({ ...DEFAULT_CONFIG, ...channel.config })
    setAssistPanelConfigText(formatAssistPanelConfig(channel.config.assist_panel_config))
    setAssistPanelPreviewConfig(channel.config.assist_panel_config ?? {})
    setSavedChannelKey(channel.channel_key)
    setInitialized(true)
  }, [isNew, channel, initialized])

  const [savedSnapshot, setSavedSnapshot] = useState('')
  useEffect(() => {
    if (isNew) { setSavedSnapshot(''); return }
    if (channel && initialized) {
      setSavedSnapshot(
        JSON.stringify({
          name: channel.name.trim(),
          access_mode: channel.access_mode ?? 'url',
          logo_url: channel.logo_url ?? null,
          favicon_url: channel.favicon_url ?? null,
          config: { ...DEFAULT_CONFIG, ...channel.config },
          assist_panel_config_text: formatAssistPanelConfig(channel.config.assist_panel_config),
        }),
      )
    }
  }, [isNew, channel, initialized])

  const currentSnapshot = useMemo(
    () => JSON.stringify({ name: name.trim(), access_mode: accessMode, logo_url: logoUrl.trim() || null, favicon_url: faviconUrl.trim() || null, config, assist_panel_config_text: assistPanelConfigText }),
    [name, accessMode, logoUrl, faviconUrl, config, assistPanelConfigText],
  )

  const emptySnapshot = JSON.stringify({ name: '', access_mode: 'url', logo_url: null, favicon_url: null, config: DEFAULT_CONFIG, assist_panel_config_text: formatAssistPanelConfig({}) })
  const isDirty = isNew ? currentSnapshot !== emptySnapshot : currentSnapshot !== savedSnapshot

  const updateConfig = useCallback(<K extends keyof ChannelConfig>(key: K, val: ChannelConfig[K]) =>
    setConfig((c) => ({ ...c, [key]: val })), [])

  const handleLogoClick = () => {
    setLogoError('')
    logoFileRef.current?.click()
  }

  const handleLogoFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setLogoError('')
    if (file.size > MAX_LOGO_BYTES) {
      setLogoError(t('ch.form.upload.tooLarge', locale))
      if (logoFileRef.current) logoFileRef.current.value = ''
      return
    }
    try {
      const url = await logoUploadMut.mutateAsync(file)
      setLogoUrl(url)
    } catch {
      setLogoError(t('ch.form.upload.failed', locale))
    }
    if (logoFileRef.current) logoFileRef.current.value = ''
  }

  const handleFaviconClick = () => {
    setFaviconError('')
    faviconFileRef.current?.click()
  }

  const handleFaviconFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setFaviconError('')
    if (file.size > MAX_FAVICON_BYTES) {
      setFaviconError(t('ch.form.favicon.tooLarge', locale))
      if (faviconFileRef.current) faviconFileRef.current.value = ''
      return
    }
    try {
      const url = await faviconUploadMut.mutateAsync(file)
      setFaviconUrl(url)
    } catch {
      setFaviconError(t('ch.form.favicon.failed', locale))
    }
    if (faviconFileRef.current) faviconFileRef.current.value = ''
  }

  const handleBotAvatarClick = () => {
    setBotAvatarError('')
    botAvatarFileRef.current?.click()
  }

  const handleBotAvatarFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBotAvatarError('')
    if (file.size > MAX_BOT_AVATAR_BYTES) {
      setBotAvatarError(t('ch.form.openAgent.avatar.tooLarge', locale))
      if (botAvatarFileRef.current) botAvatarFileRef.current.value = ''
      return
    }
    try {
      const url = await botAvatarUploadMut.mutateAsync(file)
      updateConfig('open_agent_avatar_url', url)
    } catch {
      setBotAvatarError(t('ch.form.openAgent.avatar.failed', locale))
    }
    if (botAvatarFileRef.current) botAvatarFileRef.current.value = ''
  }

  const goBack = () => {
    if (isDirty && typeof window !== 'undefined' && !window.confirm(t('ch.form.leaveConfirm', locale))) return
    router.push('/channels/web')
  }

  const handleAssistPanelPreview = () => {
    setAssistPanelTitleError('')
    setAssistPanelCodeError('')
    setAssistPanelConfigError('')
    setAssistPanelPreviewStatus('')

    const assistTitle = config.assist_panel_title?.trim() ?? ''
    const assistCode = config.assist_panel_react_code?.trim() ?? ''
    const parsed = parseAssistPanelConfig(assistPanelConfigText)

    if (assistTitle.length > 40) {
      setAssistPanelTitleError(t('ch.form.assistPanel.title.max', locale))
      return
    }
    if (!assistCode) {
      setAssistPanelCodeError(t('ch.form.assistPanel.code.required', locale))
      return
    }
    if (!validateAssistPanelCode(assistCode)) {
      setAssistPanelCodeError(t('ch.form.assistPanel.code.invalid', locale))
      return
    }
    if (!parsed.ok) {
      setAssistPanelConfigError(t('ch.form.assistPanel.config.invalid', locale))
      return
    }

    updateConfig('assist_panel_config', parsed.value)
    setAssistPanelConfigText(formatAssistPanelConfig(parsed.value))
    setAssistPanelPreviewConfig(parsed.value)
    setAssistPanelPreviewStatus(t('ch.form.assistPanel.preview.success', locale))
  }

  const handleSave = async () => {
    const trimmed = name.trim()
    if (!trimmed || trimmed.length > 64) return
    setServiceConfigError('')
    setOpenAgentConfigError('')
    setOpenAgentAgentError('')
    setOpenAgentBotServiceHoursError('')
    setOpenAgentInputPlaceholderError('')
    setOpenAgentHandoffLabelError('')
    setOpenAgentHandoffThresholdError('')
    setOpenAgentCustomButtonsError('')
    setHumanCustomButtonsError('')
    setOfflineTitleError('')
    setOfflineMessageError('')
    setLeaveMessagePromptError('')
    setQueueMessageError('')
    setQueueFullMessageError('')
    setQueueFullButtonLabelError('')
    setAssistPanelTitleError('')
    setAssistPanelCodeError('')
    setAssistPanelConfigError('')
    setAssistPanelPreviewStatus('')
    if (config.service_hours_enabled && !config.service_hours_id) {
      setActiveTab('service')
      setServiceConfigError(t('ch.form.serviceHours.required', locale))
      return
    }
    if (config.open_agent_enabled) {
      if (!openAgentConfigured) {
        setActiveTab('service')
        setOpenAgentConfigError(t('ch.form.openAgent.configRequired', locale))
        return
      }
      if (!config.open_agent_agent_id) {
        setActiveTab('service')
        setOpenAgentAgentError(t('ch.form.openAgent.agent.required', locale))
        return
      }
      if (config.open_agent_bot_strategy === 'service_hours' && !config.open_agent_bot_service_hours_id) {
        setActiveTab('service')
        setOpenAgentBotServiceHoursError(t('ch.form.openAgent.botServiceHours.required', locale))
        return
      }
      if ((config.open_agent_input_placeholder ?? '').trim().length > 50) {
        setActiveTab('service')
        setOpenAgentInputPlaceholderError(t('ch.form.openAgent.inputPlaceholder.max', locale))
        return
      }
      if (config.open_agent_handoff_enabled) {
        const handoffLabel = config.open_agent_handoff_label.trim()
        if (!handoffLabel) {
          setActiveTab('service')
          setOpenAgentHandoffLabelError(t('ch.form.openAgent.handoffLabel.required', locale))
          return
        }
        if (handoffLabel.length > 16) {
          setActiveTab('service')
          setOpenAgentHandoffLabelError(t('ch.form.openAgent.handoffLabel.max', locale))
          return
        }
        if (
          !Number.isInteger(config.open_agent_handoff_after_messages)
          || config.open_agent_handoff_after_messages < 1
          || config.open_agent_handoff_after_messages > 99
        ) {
          setActiveTab('service')
          setOpenAgentHandoffThresholdError(t('ch.form.openAgent.handoffThreshold.invalid', locale))
          return
        }
      }
    }
    const openAgentCustomButtonError = validateCustomButtonGroup(config.open_agent_custom_buttons, locale)
    if (openAgentCustomButtonError) {
      setActiveTab('service')
      setOpenAgentCustomButtonsError(openAgentCustomButtonError)
      return
    }
    const humanCustomButtonError = validateCustomButtonGroup(config.human_custom_buttons, locale)
    if (humanCustomButtonError) {
      setActiveTab('service')
      setHumanCustomButtonsError(humanCustomButtonError)
      return
    }
    if (config.outside_service_hours_strategy === 'offline_message') {
      if (!config.offline_title.trim()) {
        setActiveTab('service')
        setOfflineTitleError(t('ch.form.offlineTitle.required', locale))
        return
      }
      if (!stripHtml(config.offline_message)) {
        setActiveTab('service')
        setOfflineMessageError(t('ch.form.offlineMessage.required', locale))
        return
      }
    }
    if (config.outside_service_hours_strategy === 'leave_message' && !stripHtml(config.leave_message_prompt)) {
      setActiveTab('service')
      setLeaveMessagePromptError(t('ch.form.leaveMessagePrompt.required', locale))
      return
    }
    if (!stripHtml(config.queue_message)) {
      setActiveTab('service')
      setQueueMessageError(t('ch.form.queueMessage.required', locale))
      return
    }
    if (!stripHtml(config.queue_full_message)) {
      setActiveTab('service')
      setQueueFullMessageError(t('ch.form.queueFullMessage.required', locale))
      return
    }
    if (config.queue_full_show_leave_message_button) {
      const label = config.queue_full_leave_message_button_label.trim()
      if (!label) {
        setActiveTab('service')
        setQueueFullButtonLabelError(t('ch.form.queueFullButtonLabel.required', locale))
        return
      }
      if (label.length > 16) {
        setActiveTab('service')
        setQueueFullButtonLabelError(t('ch.form.queueFullButtonLabel.max', locale))
        return
      }
    }
    let assistPanelConfig = config.assist_panel_config
    if (config.assist_panel_enabled) {
      const assistTitle = config.assist_panel_title?.trim() ?? ''
      const assistCode = config.assist_panel_react_code?.trim() ?? ''
      const parsed = parseAssistPanelConfig(assistPanelConfigText)
      if (assistTitle.length > 40) {
        setActiveTab('assist')
        setAssistPanelTitleError(t('ch.form.assistPanel.title.max', locale))
        return
      }
      if (!assistCode) {
        setActiveTab('assist')
        setAssistPanelCodeError(t('ch.form.assistPanel.code.required', locale))
        return
      }
      if (!validateAssistPanelCode(assistCode)) {
        setActiveTab('assist')
        setAssistPanelCodeError(t('ch.form.assistPanel.code.invalid', locale))
        return
      }
      if (!parsed.ok) {
        setActiveTab('assist')
        setAssistPanelConfigError(t('ch.form.assistPanel.config.invalid', locale))
        return
      }
      assistPanelConfig = parsed.value
    } else {
      const parsed = parseAssistPanelConfig(assistPanelConfigText)
      if (parsed.ok) assistPanelConfig = parsed.value
    }
    const nextAssistPanelConfigText = formatAssistPanelConfig(assistPanelConfig)
    const nextConfig = {
      ...config,
      outside_service_hours_strategy: config.outside_service_hours_strategy,
      offline_title: config.offline_title.trim(),
      leave_message_prompt: config.leave_message_prompt || DEFAULT_LEAVE_MESSAGE_PROMPT,
      queue_message: config.queue_message || DEFAULT_QUEUE_MESSAGE,
      queue_full_message: config.queue_full_message || DEFAULT_QUEUE_FULL_MESSAGE,
      queue_full_leave_message_button_label: (
        config.queue_full_leave_message_button_label.trim()
        || DEFAULT_QUEUE_FULL_LEAVE_MESSAGE_BUTTON_LABEL
      ),
      open_agent_agent_name: selectedOpenAgent?.name ?? config.open_agent_agent_name,
      open_agent_bot_service_hours_id:
        config.open_agent_bot_strategy === 'service_hours' ? config.open_agent_bot_service_hours_id : null,
      open_agent_avatar_url: config.open_agent_avatar_url?.trim() || null,
      open_agent_input_placeholder: config.open_agent_input_placeholder?.trim() || null,
      open_agent_handoff_label: config.open_agent_handoff_label.trim() || DEFAULT_OPEN_AGENT_HANDOFF_LABEL,
      open_agent_custom_buttons: normalizeCustomButtonGroup(config.open_agent_custom_buttons),
      human_custom_buttons: normalizeCustomButtonGroup(config.human_custom_buttons),
      assist_panel_title: config.assist_panel_title?.trim() || null,
      assist_panel_react_code: config.assist_panel_react_code?.trim() || null,
      assist_panel_config: assistPanelConfig,
    }
    const body: CreateChannelPayload = {
      name: trimmed,
      channel_type: 'web',
      access_mode: accessMode,
      logo_url: logoUrl.trim() || null,
      favicon_url: faviconUrl.trim() || null,
      config: nextConfig,
    }
    const snap = JSON.stringify({ name: trimmed, access_mode: accessMode, logo_url: body.logo_url ?? null, favicon_url: body.favicon_url ?? null, config: nextConfig, assist_panel_config_text: nextAssistPanelConfigText })
    try {
      if (isNew || !savedId) {
        const created = await createMut.mutateAsync(body)
        setSavedId(created.id)
        setSavedChannelKey(created.channel_key)
        setConfig(nextConfig)
        setAssistPanelConfigText(nextAssistPanelConfigText)
        setAssistPanelPreviewConfig(assistPanelConfig)
        setSavedSnapshot(snap)
        router.replace(`/channels/web/${created.id}`)
      } else {
        await updateMut.mutateAsync({ id: savedId, data: body })
        setConfig(nextConfig)
        setAssistPanelConfigText(nextAssistPanelConfigText)
        setAssistPanelPreviewConfig(assistPanelConfig)
        setSavedSnapshot(snap)
      }
    } catch { /* error handled by mutation */ }
  }

  const saveDisabled = createMut.isPending || updateMut.isPending || !isDirty || !name.trim()

  if (!isNew && isLoading) return <p className="p-8 text-sm text-muted-foreground">{t('ch.loading', locale)}</p>
  if (!isNew && !channel && !isLoading) return <p className="p-8 text-sm text-red-600">Not found</p>

  const title = isNew
    ? t('ch.new.title', locale)
    : t('ch.edit.title', locale, { name: channel?.name ?? '' })
  const showSavedOpenAgentOption = Boolean(
    config.open_agent_agent_id
    && !openAgentAgentItems.some((item) => item.id === config.open_agent_agent_id),
  )

  return (
    <div className="-m-8 flex flex-col">
      {/* Sticky top bar — h-14 (56px), px-6 (24px); -top-8 compensates for <main>'s p-8 */}
      <div className="sticky -top-8 z-20 flex h-14 items-center justify-between border-b border-border bg-white px-6">
        <button type="button" onClick={goBack} className="flex items-center gap-2 transition-colors">
          <IconArrowLeft size={20} className="text-muted-foreground" />
          <span className="text-base font-semibold text-foreground">{title}</span>
        </button>
        <button
          type="button"
          disabled={saveDisabled}
          onClick={handleSave}
          className="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-40"
        >
          {createMut.isPending || updateMut.isPending ? t('ch.saving', locale) : t('ch.save', locale)}
        </button>
      </div>

      {/* Scroll area — padding 32, gap 24 */}
      <div className="flex-1 overflow-y-auto p-8">
        {/* Form shell — padding 24, gap 24 */}
        <div className={`flex flex-col gap-6 p-6 ${
          activeTab === 'assist' ? 'w-full max-w-[1180px]' : 'w-[720px]'
        }`}>
          <StandardTabSwitch
            options={[
              { value: 'interface' as const, label: t('ch.tab.interface', locale) },
              { value: 'service' as const, label: t('ch.tab.service', locale) },
              { value: 'assist' as const, label: t('ch.tab.assist', locale) },
            ]}
            value={activeTab}
            onChange={setActiveTab}
          />

          {activeTab === 'interface' && (
            <>
          {/* ── Section 0: Access info display ── */}
          <SectionTitle>{t('ch.section.accessMode', locale)}</SectionTitle>
          <SegmentedControl
            options={[
              { value: 'url' as const, label: t('ch.accessMode.url', locale) },
              { value: 'embed' as const, label: t('ch.accessMode.embed', locale) },
            ]}
            value={accessMode}
            onChange={setAccessMode}
          />
          {savedChannelKey && (
            accessMode === 'url'
              ? <AccessLinkSection url={`${typeof window !== 'undefined' ? window.location.origin : ''}/chat/${savedChannelKey}`} />
              : <EmbedCodeSection channelKey={savedChannelKey} />
          )}

          <Separator />

          {/* ── Section 1: Basic Info ── */}
          <SectionTitle>{t('ch.section.basic', locale)}</SectionTitle>
          <div className="flex flex-col gap-2">
            <FieldLabel label={t('ch.form.name', locale)} required />
            <TextInput
              value={name}
              onChange={setName}
              placeholder={t('ch.form.name.placeholder', locale)}
            />
          </div>

          <Separator />

          {/* ── Section 2: Appearance ── */}
          <SectionTitle>{t('ch.section.appearance', locale)}</SectionTitle>

          {/* Sub: Page background */}
          <SubSectionTitle>{t('ch.section.pageBg', locale)}</SubSectionTitle>
          <ChannelColorField
            label={t('ch.form.pageBgColor', locale)}
            value={channelColorPreview(config.page_bg_color, CHANNEL_COLOR_PREVIEW.pageBg)}
            onChange={(v) => updateConfig('page_bg_color', v)}
          />

          <Separator />

          {/* Sub: Page & Browser */}
          <SubSectionTitle>{t('ch.section.pageBrowser', locale)}</SubSectionTitle>
          <div className="flex flex-col gap-2">
            <FieldLabel label={t('ch.form.documentTitle', locale)} />
            <TextInput
              value={config.document_title ?? ''}
              onChange={(v) => updateConfig('document_title', v || null)}
              placeholder={t('ch.form.documentTitle.placeholder', locale)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <FieldLabel label={t('ch.form.favicon', locale)} />
            <input
              ref={faviconFileRef}
              type="file"
              accept="image/x-icon,image/vnd.microsoft.icon,image/png,image/svg+xml,image/webp"
              onChange={handleFaviconFileChange}
              className="hidden"
            />
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleFaviconClick}
                disabled={faviconUploadMut.isPending}
                className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-lg border border-dashed border-border bg-white transition-colors hover:bg-accent/50 disabled:opacity-50"
              >
                {faviconUploadMut.isPending ? (
                  <IconLoader2 size={20} className="animate-spin text-muted-foreground" />
                ) : faviconUrl ? (
                  <img src={faviconUrl} alt="favicon" className="max-h-[48px] max-w-[48px] object-contain" />
                ) : (
                  <IconUpload size={20} className="text-border" />
                )}
              </button>
              {faviconUrl && (
                <button
                  type="button"
                  onClick={() => setFaviconUrl('')}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
                >
                  <IconTrash size={16} />
                </button>
              )}
            </div>
            {faviconError
              ? <span className="text-xs text-destructive">{faviconError}</span>
              : <span className="text-xs text-muted-foreground">{t('ch.form.favicon.hint', locale)}</span>
            }
          </div>

          <Separator />

          {/* Sub: Header (separated from Page & Browser above by Separator) */}
          <SubSectionTitle>{t('ch.section.header', locale)}</SubSectionTitle>
          {/* Logo upload — same pattern as employee avatar (hidden input + button click) */}
          <div className="flex flex-col gap-2">
            <FieldLabel label={t('ch.form.logo', locale)} />
            <input
              ref={logoFileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/svg+xml"
              onChange={handleLogoFileChange}
              className="hidden"
            />
            <div className="flex items-end gap-3">
              <button
                type="button"
                onClick={handleLogoClick}
                disabled={logoUploadMut.isPending}
                className="flex h-[120px] w-[120px] items-center justify-center overflow-hidden rounded-lg border border-dashed border-border bg-white transition-colors hover:bg-accent/50 disabled:opacity-50"
              >
                {logoUploadMut.isPending ? (
                  <IconLoader2 size={24} className="animate-spin text-muted-foreground" />
                ) : logoUrl ? (
                  <img src={logoUrl} alt="logo" className="max-h-[100px] max-w-[100px] object-contain" />
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <IconUpload size={24} className="text-border" />
                    <span className="text-xs text-muted-foreground">{t('ch.form.upload', locale)}</span>
                  </div>
                )}
              </button>
              {logoUrl && (
                <button
                  type="button"
                  onClick={() => setLogoUrl('')}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
                >
                  <IconTrash size={16} />
                </button>
              )}
            </div>
            {logoError
              ? <span className="text-xs text-destructive">{logoError}</span>
              : <span className="text-xs text-muted-foreground">{t('ch.form.upload.hint', locale)}</span>
            }
          </div>
          <div className="flex flex-col gap-2">
            <FieldLabel label={t('ch.form.title', locale)} />
            <TextInput
              value={config.title ?? ''}
              onChange={(v) => updateConfig('title', v || null)}
              placeholder={t('ch.form.title.placeholder', locale)}
            />
          </div>
          {/* Gradient colors — side by side, gap 16 */}
          <div className="flex gap-4">
            <ChannelColorField
              label={t('ch.form.gradientStart', locale)}
              value={channelColorPreview(config.header_gradient_start, CHANNEL_COLOR_PREVIEW.headerGradient)}
              onChange={(v) => updateConfig('header_gradient_start', v)}
            />
            <ChannelColorField
              label={t('ch.form.gradientEnd', locale)}
              value={channelColorPreview(config.header_gradient_end, CHANNEL_COLOR_PREVIEW.headerGradient)}
              onChange={(v) => updateConfig('header_gradient_end', v)}
            />
          </div>
          <ChannelColorField label={t('ch.form.titleColor', locale)} value={config.header_title_color ?? '#FFFFFF'} onChange={(v) => updateConfig('header_title_color', v)} />

          <Separator />

          {/* Sub: Messages */}
          <SubSectionTitle>{t('ch.section.messages', locale)}</SubSectionTitle>
          <ChannelColorField
            label={t('ch.form.messageAreaBg', locale)}
            value={channelColorPreview(config.message_area_bg_color, CHANNEL_COLOR_PREVIEW.messageAreaBg)}
            onChange={(v) => updateConfig('message_area_bg_color', v)}
          />

          <Separator />

          {/* Sub: Agent Bubble — 3 swatches in a row, gap 12 */}
          <SubSectionTitle>{t('ch.section.agentBubble', locale)}</SubSectionTitle>
          <div className="flex gap-3">
            <ChannelColorField
              label={t('ch.form.bubbleBg', locale)}
              value={channelColorPreview(config.agent_bubble_bg_color, CHANNEL_COLOR_PREVIEW.agentBubbleBg)}
              onChange={(v) => updateConfig('agent_bubble_bg_color', v)}
              labelSize={13}
            />
            <ChannelColorField
              label={t('ch.form.bubbleText', locale)}
              value={channelColorPreview(config.agent_bubble_text_color, CHANNEL_COLOR_PREVIEW.agentBubbleText)}
              onChange={(v) => updateConfig('agent_bubble_text_color', v)}
              labelSize={13}
            />
            <ChannelColorField label={t('ch.form.bubbleBorder', locale)} value={config.agent_bubble_border_color ?? ''} onChange={(v) => updateConfig('agent_bubble_border_color', v)} labelSize={13} />
          </div>
          <RadiusField label={t('ch.form.bubbleRadius', locale)} value={config.agent_bubble_radius} onChange={(v) => updateConfig('agent_bubble_radius', v)} />
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-start justify-between gap-6">
              <div className="flex flex-col gap-1">
                <FieldLabel label={t('ch.form.useAgentAvatar', locale)} />
                <p className="text-xs leading-5 text-muted-foreground">
                  {t('ch.form.useAgentAvatar.hint', locale)}
                </p>
              </div>
              <Switch
                checked={config.use_agent_avatar}
                onCheckedChange={(v) => updateConfig('use_agent_avatar', v)}
              />
            </div>
          </div>

          <Separator />

          {/* Sub: User Bubble — same layout */}
          <SubSectionTitle>{t('ch.section.userBubble', locale)}</SubSectionTitle>
          <div className="flex gap-3">
            <ChannelColorField
              label={t('ch.form.bubbleBg', locale)}
              value={channelColorPreview(config.user_bubble_bg_color, CHANNEL_COLOR_PREVIEW.userBubbleBg)}
              onChange={(v) => updateConfig('user_bubble_bg_color', v)}
              labelSize={13}
            />
            <ChannelColorField
              label={t('ch.form.bubbleText', locale)}
              value={channelColorPreview(config.user_bubble_text_color, CHANNEL_COLOR_PREVIEW.userBubbleText)}
              onChange={(v) => updateConfig('user_bubble_text_color', v)}
              labelSize={13}
            />
            <ChannelColorField label={t('ch.form.bubbleBorder', locale)} value={config.user_bubble_border_color ?? ''} onChange={(v) => updateConfig('user_bubble_border_color', v)} labelSize={13} />
          </div>
          <RadiusField label={t('ch.form.bubbleRadius', locale)} value={config.user_bubble_radius} onChange={(v) => updateConfig('user_bubble_radius', v)} />

          {/* Sub: Embed Button — only visible in embed mode */}
          {accessMode === 'embed' && (
            <>
              <Separator />
              <SubSectionTitle>{t('ch.section.embedButton', locale)}</SubSectionTitle>
              <div className="flex gap-3">
                <ChannelColorField
                  label={t('ch.form.embedBtnBg', locale)}
                  value={channelColorPreview(config.embed_button_bg_color, CHANNEL_COLOR_PREVIEW.embedBtnBg)}
                  onChange={(v) => updateConfig('embed_button_bg_color', v)}
                  labelSize={13}
                />
                <ChannelColorField
                  label={t('ch.form.embedBtnIcon', locale)}
                  value={channelColorPreview(config.embed_button_icon_color, CHANNEL_COLOR_PREVIEW.embedBtnIcon)}
                  onChange={(v) => updateConfig('embed_button_icon_color', v)}
                  labelSize={13}
                />
              </div>
            </>
          )}

          <Separator />

          <div className="flex flex-col gap-2">
            <FieldLabel label={t('ch.form.inputPlaceholder', locale)} />
            <TextInput
              value={config.input_placeholder ?? ''}
              onChange={(v) => updateConfig('input_placeholder', v || null)}
              placeholder={t('ch.form.inputPlaceholder.placeholder', locale)}
            />
          </div>

          <ChannelColorField
            label={t('ch.form.sendButtonBg', locale)}
            value={channelColorPreview(config.send_button_bg_color, CHANNEL_COLOR_PREVIEW.sendButtonBg)}
            onChange={(v) => updateConfig('send_button_bg_color', v)}
          />

          {/* Access info is now shown in the Access Mode section above */}
            </>
          )}

          {activeTab === 'service' && (
            <>
              <SectionTitle>{t('ch.section.serviceConfig', locale)}</SectionTitle>
              <div className="rounded-lg border border-border bg-card p-5">
                <div className="flex items-start justify-between gap-6">
                  <div className="flex flex-col gap-1">
                    <FieldLabel label={t('ch.form.serviceHours', locale)} />
                    <p className="text-xs leading-5 text-muted-foreground">
                      {t('ch.form.serviceHours.hint', locale)}
                    </p>
                  </div>
                  <Switch
                    checked={config.service_hours_enabled}
                    onCheckedChange={(v) => {
                      updateConfig('service_hours_enabled', v)
                      if (!v) updateConfig('service_hours_id', null)
                      setServiceConfigError('')
                    }}
                  />
                </div>

                {config.service_hours_enabled && (
                  <div className="mt-4 flex flex-col gap-2">
                    <FieldLabel label={t('ch.form.serviceHours.select', locale)} required />
                    <select
                      value={config.service_hours_id ?? ''}
                      disabled={serviceHoursLoading}
                      onChange={(e) => {
                        updateConfig('service_hours_id', e.target.value ? Number(e.target.value) : null)
                        setServiceConfigError('')
                      }}
                      className="h-10 w-full rounded-lg border border-border bg-white px-3.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
                    >
                      <option value="">
                        {serviceHoursLoading
                          ? t('ch.form.serviceHours.loading', locale)
                          : t('ch.form.serviceHours.placeholder', locale)}
                      </option>
                      {serviceHours.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.description ? `${item.name} - ${item.description}` : item.name}
                        </option>
                      ))}
                    </select>
                    {serviceHours.length === 0 && !serviceHoursLoading && (
                      <p className="text-xs text-muted-foreground">{t('ch.form.serviceHours.empty', locale)}</p>
                    )}
                    {serviceConfigError && <p className="text-xs text-destructive">{serviceConfigError}</p>}
                  </div>
                )}
              </div>

              <div className="rounded-lg border border-border bg-card p-5">
                <div className="flex flex-col gap-2">
                  <FieldLabel label={t('ch.form.outsideServiceHoursStrategy', locale)} required />
                  <p className="text-xs leading-5 text-muted-foreground">
                    {t('ch.form.outsideServiceHoursStrategy.hint', locale)}
                  </p>
                  <SegmentedControl
                    options={[
                      { value: 'offline_message' as const, label: t('ch.form.outsideServiceHoursStrategy.offline', locale) },
                      { value: 'leave_message' as const, label: t('ch.form.outsideServiceHoursStrategy.leaveMessage', locale) },
                    ]}
                    value={config.outside_service_hours_strategy}
                    onChange={(v) => {
                      updateConfig('outside_service_hours_strategy', v)
                      setOfflineTitleError('')
                      setOfflineMessageError('')
                      setLeaveMessagePromptError('')
                    }}
                  />
                </div>

                {config.outside_service_hours_strategy === 'leave_message' && (
                  <div className="mt-5 flex flex-col gap-2">
                    <FieldLabel label={t('ch.form.leaveMessagePrompt', locale)} required />
                    <p className="text-xs leading-5 text-muted-foreground">
                      {t('ch.form.leaveMessagePrompt.hint', locale)}
                    </p>
                    <RichTextFieldEditor
                      value={config.leave_message_prompt}
                      onChange={(v) => {
                        updateConfig('leave_message_prompt', v ?? '')
                        setLeaveMessagePromptError('')
                      }}
                      placeholder={t('ch.form.leaveMessagePrompt.placeholder', locale)}
                    />
                    {leaveMessagePromptError && <p className="text-xs text-destructive">{leaveMessagePromptError}</p>}
                  </div>
                )}
              </div>

              <div className="rounded-lg border border-border bg-card p-5">
                <div className="flex flex-col gap-5">
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between gap-3">
                      <FieldLabel label={t('ch.form.queueMessage', locale)} required />
                      <button
                        type="button"
                        onClick={() => {
                          updateConfig('queue_message', `${config.queue_message || ''}${QUEUE_COUNT_VARIABLE}`)
                          setQueueMessageError('')
                        }}
                        className="rounded-md border border-border bg-white px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent"
                      >
                        {t('ch.form.queueMessage.insertVariable', locale)}
                      </button>
                    </div>
                    <p className="text-xs leading-5 text-muted-foreground">
                      {t('ch.form.queueMessage.hint', locale)}
                    </p>
                    <RichTextFieldEditor
                      value={config.queue_message}
                      onChange={(v) => {
                        updateConfig('queue_message', v ?? '')
                        setQueueMessageError('')
                      }}
                      placeholder={DEFAULT_QUEUE_MESSAGE}
                    />
                    {queueMessageError && <p className="text-xs text-destructive">{queueMessageError}</p>}
                  </div>

                  <div className="flex flex-col gap-2">
                    <FieldLabel label={t('ch.form.queueFullMessage', locale)} required />
                    <p className="text-xs leading-5 text-muted-foreground">
                      {t('ch.form.queueFullMessage.hint', locale)}
                    </p>
                    <RichTextFieldEditor
                      value={config.queue_full_message}
                      onChange={(v) => {
                        updateConfig('queue_full_message', v ?? '')
                        setQueueFullMessageError('')
                      }}
                      placeholder={DEFAULT_QUEUE_FULL_MESSAGE}
                    />
                    {queueFullMessageError && <p className="text-xs text-destructive">{queueFullMessageError}</p>}
                  </div>

                  <div className="rounded-lg border border-border bg-white p-4">
                    <div className="flex items-start justify-between gap-6">
                      <div className="flex flex-col gap-1">
                        <FieldLabel label={t('ch.form.queueFullButton', locale)} />
                        <p className="text-xs leading-5 text-muted-foreground">
                          {t('ch.form.queueFullButton.hint', locale)}
                        </p>
                      </div>
                      <Switch
                        checked={config.queue_full_show_leave_message_button}
                        onCheckedChange={(v) => {
                          updateConfig('queue_full_show_leave_message_button', v)
                          setQueueFullButtonLabelError('')
                        }}
                      />
                    </div>
                    {config.queue_full_show_leave_message_button && (
                      <div className="mt-4 flex flex-col gap-2">
                        <FieldLabel label={t('ch.form.queueFullButtonLabel', locale)} required />
                        <TextInput
                          value={config.queue_full_leave_message_button_label}
                          onChange={(v) => {
                            updateConfig('queue_full_leave_message_button_label', v)
                            setQueueFullButtonLabelError('')
                          }}
                          placeholder={DEFAULT_QUEUE_FULL_LEAVE_MESSAGE_BUTTON_LABEL}
                        />
                        {queueFullButtonLabelError && <p className="text-xs text-destructive">{queueFullButtonLabelError}</p>}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="rounded-lg border border-border bg-card p-5">
                <CustomButtonGroupEditor
                  title={t('ch.form.humanCustomButtons', locale)}
                  hint={t('ch.form.humanCustomButtons.hint', locale)}
                  enabled={config.human_custom_buttons_enabled}
                  buttons={config.human_custom_buttons}
                  error={humanCustomButtonsError}
                  onEnabledChange={(v) => updateConfig('human_custom_buttons_enabled', v)}
                  onButtonsChange={(buttons) => updateConfig('human_custom_buttons', buttons)}
                  onErrorClear={() => setHumanCustomButtonsError('')}
                />
              </div>

              <div className="rounded-lg border border-border bg-card p-5">
                <div className="flex items-start justify-between gap-6">
                  <div className="flex flex-col gap-1">
                    <FieldLabel label={t('ch.form.openAgent.enabled', locale)} />
                    <p className="text-xs leading-5 text-muted-foreground">
                      {t('ch.form.openAgent.enabled.hint', locale)}
                    </p>
                  </div>
                  <Switch
                    checked={config.open_agent_enabled}
                    disabled={openAgentSettingsLoading}
                    onCheckedChange={(v) => {
                      setOpenAgentConfigError('')
                      if (v && !openAgentConfigured) {
                        setOpenAgentConfigError(t('ch.form.openAgent.configRequired', locale))
                        return
                      }
                      updateConfig('open_agent_enabled', v)
                    }}
                  />
                </div>

                {!openAgentConfigured && (
                  <div className="mt-4 flex items-start gap-3 rounded-lg border border-warning/30 bg-warning/10 p-3">
                    <IconAlertCircle size={18} className="mt-0.5 shrink-0 text-warning" />
                    <div className="flex flex-1 flex-col gap-2">
                      <p className="text-xs leading-5 text-foreground">
                        {t('ch.form.openAgent.configRequired', locale)}
                      </p>
                      <button
                        type="button"
                        onClick={() => router.push('/open-agent-settings')}
                        className="w-fit rounded-md border border-border bg-white px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent"
                      >
                        {t('ch.form.openAgent.goSettings', locale)}
                      </button>
                    </div>
                  </div>
                )}
                {openAgentConfigError && <p className="mt-3 text-xs text-destructive">{openAgentConfigError}</p>}

                {config.open_agent_enabled && (
                  <div className="mt-5 flex flex-col gap-5">
                    <div className="flex flex-col gap-2">
                      <div className="flex items-center justify-between gap-3">
                        <FieldLabel label={t('ch.form.openAgent.agent', locale)} required />
                        <button
                          type="button"
                          onClick={() => void refetchOpenAgentAgents()}
                          disabled={!openAgentConfigured || openAgentAgentsFetching}
                          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-3 text-xs font-medium text-foreground/80 transition-colors hover:bg-accent disabled:opacity-50"
                        >
                          <IconRefresh size={14} className={openAgentAgentsFetching ? 'animate-spin' : ''} />
                          {t('ch.form.openAgent.refreshAgents', locale)}
                        </button>
                      </div>
                      <select
                        value={config.open_agent_agent_id ?? ''}
                        disabled={!openAgentConfigured || openAgentAgentsFetching}
                        onChange={(e) => {
                          const agentId = e.target.value ? Number(e.target.value) : null
                          const agent = openAgentAgentItems.find((item) => item.id === agentId)
                          updateConfig('open_agent_agent_id', agentId)
                          updateConfig('open_agent_agent_name', agent?.name ?? null)
                          setOpenAgentAgentError('')
                        }}
                        className="h-10 w-full rounded-lg border border-border bg-white px-3.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
                      >
                        <option value="">
                          {openAgentAgentsFetching
                            ? t('ch.form.openAgent.agent.loading', locale)
                            : t('ch.form.openAgent.agent.placeholder', locale)}
                        </option>
                        {showSavedOpenAgentOption && (
                          <option value={config.open_agent_agent_id ?? ''}>
                            {t('ch.form.openAgent.agent.pending', locale, {
                              name: config.open_agent_agent_name ?? `#${config.open_agent_agent_id}`,
                            })}
                          </option>
                        )}
                        {openAgentAgentItems.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name}
                          </option>
                        ))}
                      </select>
                      {openAgentAgentsIsError && (
                        <p className="text-xs text-destructive">{t('ch.form.openAgent.agent.loadFailed', locale)}</p>
                      )}
                      {openAgentAgentItems.length === 0 && !openAgentAgentsFetching && !openAgentAgentsIsError && (
                        <p className="text-xs text-muted-foreground">{t('ch.form.openAgent.agent.empty', locale)}</p>
                      )}
                      {openAgentAgentError && <p className="text-xs text-destructive">{openAgentAgentError}</p>}
                    </div>

                    <div className="flex flex-col gap-2">
                      <FieldLabel label={t('ch.form.openAgent.strategy', locale)} required />
                      <SegmentedControl
                        options={[
                          { value: 'always' as const, label: t('ch.form.openAgent.strategy.always', locale) },
                          { value: 'service_hours' as const, label: t('ch.form.openAgent.strategy.serviceHours', locale) },
                        ]}
                        value={config.open_agent_bot_strategy}
                        onChange={(v) => {
                          updateConfig('open_agent_bot_strategy', v)
                          if (v !== 'service_hours') updateConfig('open_agent_bot_service_hours_id', null)
                          setOpenAgentBotServiceHoursError('')
                        }}
                      />
                      <p className="text-xs leading-5 text-muted-foreground">
                        {t('ch.form.openAgent.strategy.hint', locale)}
                      </p>
                    </div>

                    {config.open_agent_bot_strategy === 'service_hours' && (
                      <div className="flex flex-col gap-2">
                        <FieldLabel label={t('ch.form.openAgent.botServiceHours', locale)} required />
                        <select
                          value={config.open_agent_bot_service_hours_id ?? ''}
                          disabled={serviceHoursLoading}
                          onChange={(e) => {
                            updateConfig('open_agent_bot_service_hours_id', e.target.value ? Number(e.target.value) : null)
                            setOpenAgentBotServiceHoursError('')
                          }}
                          className="h-10 w-full rounded-lg border border-border bg-white px-3.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
                        >
                          <option value="">
                            {serviceHoursLoading
                              ? t('ch.form.serviceHours.loading', locale)
                              : t('ch.form.openAgent.botServiceHours.placeholder', locale)}
                          </option>
                          {serviceHours.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.description ? `${item.name} - ${item.description}` : item.name}
                            </option>
                          ))}
                        </select>
                        {serviceHours.length === 0 && !serviceHoursLoading && (
                          <p className="text-xs text-muted-foreground">{t('ch.form.serviceHours.empty', locale)}</p>
                        )}
                        {openAgentBotServiceHoursError && <p className="text-xs text-destructive">{openAgentBotServiceHoursError}</p>}
                      </div>
                    )}

                    <div className="flex flex-col gap-2">
                      <FieldLabel label={t('ch.form.openAgent.avatar', locale)} />
                      <input
                        ref={botAvatarFileRef}
                        type="file"
                        accept="image/jpeg,image/png,image/gif,image/webp"
                        onChange={handleBotAvatarFileChange}
                        className="hidden"
                      />
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={handleBotAvatarClick}
                          disabled={botAvatarUploadMut.isPending}
                          className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-full border border-dashed border-border bg-white transition-colors hover:bg-accent/50 disabled:opacity-50"
                        >
                          {botAvatarUploadMut.isPending ? (
                            <IconLoader2 size={20} className="animate-spin text-muted-foreground" />
                          ) : config.open_agent_avatar_url ? (
                            <img src={config.open_agent_avatar_url} alt="" className="h-full w-full object-cover" />
                          ) : (
                            <IconUpload size={20} className="text-border" />
                          )}
                        </button>
                        {config.open_agent_avatar_url && (
                          <button
                            type="button"
                            onClick={() => {
                              updateConfig('open_agent_avatar_url', null)
                              setBotAvatarError('')
                            }}
                            className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
                          >
                            <IconTrash size={16} />
                          </button>
                        )}
                      </div>
                      {botAvatarError
                        ? <span className="text-xs text-destructive">{botAvatarError}</span>
                        : <span className="text-xs text-muted-foreground">{t('ch.form.openAgent.avatar.hint', locale)}</span>
                      }
                    </div>

                    <CustomButtonGroupEditor
                      title={t('ch.form.openAgent.customButtons', locale)}
                      hint={t('ch.form.openAgent.customButtons.hint', locale)}
                      enabled={config.open_agent_custom_buttons_enabled}
                      buttons={config.open_agent_custom_buttons}
                      error={openAgentCustomButtonsError}
                      onEnabledChange={(v) => updateConfig('open_agent_custom_buttons_enabled', v)}
                      onButtonsChange={(buttons) => updateConfig('open_agent_custom_buttons', buttons)}
                      onErrorClear={() => setOpenAgentCustomButtonsError('')}
                    />

                    <div className="flex flex-col gap-2">
                      <FieldLabel label={t('ch.form.openAgent.inputPlaceholder', locale)} />
                      <TextInput
                        value={config.open_agent_input_placeholder ?? ''}
                        onChange={(v) => {
                          updateConfig('open_agent_input_placeholder', v || null)
                          setOpenAgentInputPlaceholderError('')
                        }}
                        placeholder={DEFAULT_OPEN_AGENT_INPUT_PLACEHOLDER}
                      />
                      {openAgentInputPlaceholderError && <p className="text-xs text-destructive">{openAgentInputPlaceholderError}</p>}
                    </div>

                    <div className="rounded-lg border border-border bg-white p-4">
                      <div className="flex items-start justify-between gap-6">
                        <div className="flex flex-col gap-1">
                          <FieldLabel label={t('ch.form.openAgent.handoffEnabled', locale)} />
                          <p className="text-xs leading-5 text-muted-foreground">
                            {t('ch.form.openAgent.handoffEnabled.hint', locale)}
                          </p>
                        </div>
                        <Switch
                          checked={config.open_agent_handoff_enabled}
                          onCheckedChange={(v) => updateConfig('open_agent_handoff_enabled', v)}
                        />
                      </div>

                      {config.open_agent_handoff_enabled && (
                        <div className="mt-4 grid grid-cols-[1fr_180px] gap-4">
                          <div className="flex flex-col gap-2">
                            <FieldLabel label={t('ch.form.openAgent.handoffLabel', locale)} required />
                            <TextInput
                              value={config.open_agent_handoff_label}
                              onChange={(v) => {
                                updateConfig('open_agent_handoff_label', v)
                                setOpenAgentHandoffLabelError('')
                              }}
                              placeholder={DEFAULT_OPEN_AGENT_HANDOFF_LABEL}
                            />
                            {openAgentHandoffLabelError && <p className="text-xs text-destructive">{openAgentHandoffLabelError}</p>}
                          </div>
                          <div className="flex flex-col gap-2">
                            <FieldLabel label={t('ch.form.openAgent.handoffThreshold', locale)} required />
                            <input
                              type="number"
                              min={1}
                              max={99}
                              value={config.open_agent_handoff_after_messages}
                              onChange={(e) => {
                                updateConfig('open_agent_handoff_after_messages', Number(e.target.value))
                                setOpenAgentHandoffThresholdError('')
                              }}
                              className="h-10 w-full rounded-lg border border-border bg-white px-3.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                            />
                            {openAgentHandoffThresholdError && <p className="text-xs text-destructive">{openAgentHandoffThresholdError}</p>}
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="flex flex-col gap-2">
                      <FieldLabel label={t('ch.form.openAgent.handoffBehavior', locale)} required />
                      <SegmentedControl
                        options={[
                          { value: 'confirm' as const, label: t('ch.form.openAgent.handoffBehavior.confirm', locale) },
                          { value: 'auto' as const, label: t('ch.form.openAgent.handoffBehavior.auto', locale) },
                        ]}
                        value={config.open_agent_handoff_behavior}
                        onChange={(v) => updateConfig('open_agent_handoff_behavior', v)}
                      />
                    </div>
                  </div>
                )}
              </div>

              {config.outside_service_hours_strategy === 'offline_message' && (
                <>
                  <div className="flex flex-col gap-2">
                    <FieldLabel label={t('ch.form.offlineTitle', locale)} required />
                    <p className="text-xs leading-5 text-muted-foreground">
                      {t('ch.form.offlineTitle.hint', locale)}
                    </p>
                    <TextInput
                      value={config.offline_title}
                      onChange={(v) => {
                        updateConfig('offline_title', v)
                        setOfflineTitleError('')
                      }}
                      placeholder={t('ch.form.offlineTitle.placeholder', locale)}
                    />
                    {offlineTitleError && <p className="text-xs text-destructive">{offlineTitleError}</p>}
                  </div>

                  <div className="flex flex-col gap-2">
                    <FieldLabel label={t('ch.form.offlineMessage', locale)} required />
                    <p className="text-xs leading-5 text-muted-foreground">
                      {t('ch.form.offlineMessage.hint', locale)}
                    </p>
                    <RichTextFieldEditor
                      value={config.offline_message}
                      onChange={(v) => {
                        updateConfig('offline_message', v ?? '')
                        setOfflineMessageError('')
                      }}
                      placeholder={t('ch.form.offlineMessage.placeholder', locale)}
                    />
                    {offlineMessageError && <p className="text-xs text-destructive">{offlineMessageError}</p>}
                  </div>
                </>
              )}
            </>
          )}

          {activeTab === 'assist' && (
            <div className="flex flex-col gap-6 xl:flex-row xl:items-start">
              <div className="flex min-w-0 flex-1 flex-col gap-6 xl:max-w-[720px]">
                <SectionTitle>{t('ch.section.assistPanel', locale)}</SectionTitle>

                <div className="rounded-lg border border-border bg-card p-5">
                  <div className="flex items-start justify-between gap-6">
                    <div className="flex flex-col gap-1">
                      <FieldLabel label={t('ch.form.assistPanel.enabled', locale)} />
                      <p className="text-xs leading-5 text-muted-foreground">
                        {t('ch.form.assistPanel.enabled.hint', locale)}
                      </p>
                    </div>
                    <Switch
                      checked={config.assist_panel_enabled}
                      onCheckedChange={(v) => {
                        updateConfig('assist_panel_enabled', v)
                        setAssistPanelTitleError('')
                        setAssistPanelCodeError('')
                        setAssistPanelConfigError('')
                        setAssistPanelPreviewStatus('')
                        if (v && !config.assist_panel_react_code) {
                          updateConfig('assist_panel_react_code', DEFAULT_ASSIST_PANEL_CODE)
                        }
                        if (v && assistPanelConfigText === formatAssistPanelConfig({})) {
                          const nextText = formatAssistPanelConfig(DEFAULT_ASSIST_PANEL_CONFIG)
                          setAssistPanelConfigText(nextText)
                          updateConfig('assist_panel_config', DEFAULT_ASSIST_PANEL_CONFIG)
                          setAssistPanelPreviewConfig(DEFAULT_ASSIST_PANEL_CONFIG)
                        }
                      }}
                    />
                  </div>

                  <div className="mt-4 flex items-start gap-3 rounded-lg border border-border bg-background p-3">
                    <IconInfoCircle size={18} className="mt-0.5 shrink-0 text-muted-foreground" />
                    <p className="text-xs leading-5 text-muted-foreground">
                      {t('ch.form.assistPanel.modeHint', locale)}
                    </p>
                  </div>
                </div>

                {config.assist_panel_enabled && (
                  <>
                    <div className="flex flex-col gap-2">
                      <FieldLabel label={t('ch.form.assistPanel.title', locale)} />
                      <TextInput
                        value={config.assist_panel_title ?? ''}
                        onChange={(v) => {
                          updateConfig('assist_panel_title', v || null)
                          setAssistPanelTitleError('')
                        }}
                        placeholder={t('ch.form.assistPanel.title.placeholder', locale)}
                      />
                      {assistPanelTitleError && <p className="text-xs text-destructive">{assistPanelTitleError}</p>}
                    </div>

                    <div className="flex flex-col gap-2">
                      <FieldLabel label={t('ch.form.assistPanel.code', locale)} required />
                      <SourceCodeEditor
                        value={config.assist_panel_react_code ?? ''}
                        onChange={(value) => {
                          updateConfig('assist_panel_react_code', value || null)
                          setAssistPanelCodeError('')
                          setAssistPanelPreviewStatus('')
                        }}
                        placeholder={DEFAULT_ASSIST_PANEL_CODE}
                        extensions={ASSIST_PANEL_REACT_CODE_EXTENSIONS}
                        height="280px"
                        hasError={Boolean(assistPanelCodeError)}
                      />
                      {assistPanelCodeError
                        ? <p className="text-xs text-destructive">{assistPanelCodeError}</p>
                        : <p className="text-xs leading-5 text-muted-foreground">{t('ch.form.assistPanel.code.hint', locale)}</p>
                      }
                    </div>

                    <div className="flex flex-col gap-2">
                      <FieldLabel label={t('ch.form.assistPanel.config', locale)} />
                      <SourceCodeEditor
                        value={assistPanelConfigText}
                        onChange={(value) => {
                          setAssistPanelConfigText(value)
                          setAssistPanelConfigError('')
                          setAssistPanelPreviewStatus('')
                        }}
                        placeholder={formatAssistPanelConfig(DEFAULT_ASSIST_PANEL_CONFIG)}
                        extensions={ASSIST_PANEL_JSON_CODE_EXTENSIONS}
                        height="220px"
                        hasError={Boolean(assistPanelConfigError)}
                      />
                      {assistPanelConfigError
                        ? <p className="text-xs text-destructive">{assistPanelConfigError}</p>
                        : <p className="text-xs leading-5 text-muted-foreground">{t('ch.form.assistPanel.config.hint', locale)}</p>
                      }
                    </div>

                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={handleAssistPanelPreview}
                        className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-white px-4 text-sm font-medium text-foreground transition-colors hover:bg-accent"
                      >
                        <IconEye size={16} />
                        {t('ch.form.assistPanel.preview', locale)}
                      </button>
                      {assistPanelPreviewStatus && (
                        <span className="text-xs text-success">{assistPanelPreviewStatus}</span>
                      )}
                    </div>
                  </>
                )}
              </div>

              {config.assist_panel_enabled && (
                <aside className="w-full shrink-0 xl:ml-auto xl:w-[360px] xl:sticky xl:top-20">
                  <AssistPanelCodePreview
                    title={config.assist_panel_title?.trim() || t('chat.assistPanel.defaultTitle', locale)}
                    code={config.assist_panel_react_code ?? ''}
                    config={assistPanelPreviewConfig}
                  />
                </aside>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
