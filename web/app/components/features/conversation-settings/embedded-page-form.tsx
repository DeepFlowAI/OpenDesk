'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft, IconExternalLink, IconEye, IconPlayerPlay } from '@tabler/icons-react'
import CodeMirror, { type ReactCodeMirrorProps } from '@uiw/react-codemirror'
import { javascript } from '@codemirror/lang-javascript'
import { json } from '@codemirror/lang-json'
import { okaidiaInit } from '@uiw/codemirror-theme-okaidia'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { Switch } from '@/components/ui/switch'
import { getAssistPanelCodeError } from '@/app/components/features/visitor-chat/assist-panel-runtime'
import { EmbeddedPageRuntime, type EmbeddedPageApi } from '@/app/components/features/embedded-page-runtime'
import { EMBEDDED_PAGE_URL_VARIABLES_BY_LOCATION, buildEmbeddedPageUrl } from '@/utils/embedded-page'
import {
  useCreateEmbeddedPage,
  useEmbeddedPage,
  useUpdateEmbeddedPage,
} from '@/service/use-embedded-pages'
import type {
  EmbeddedPageContext,
  EmbeddedPageLocation,
  EmbeddedPageType,
  SaveEmbeddedPagePayload,
} from '@/models/embedded-page'

const CODE_BASIC_SETUP: ReactCodeMirrorProps['basicSetup'] = {
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

const REACT_CODE_EXTENSIONS: ReactCodeMirrorProps['extensions'] = [javascript({ jsx: true })]
const JSON_EXTENSIONS: ReactCodeMirrorProps['extensions'] = [json()]

const CODE_THEME = okaidiaInit({
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

const REACT_CODE_PLACEHOLDER = `export default function App({ context, config, api }) {
  const conversation = context.conversation
  return (
    <div style={{ padding: 16, fontSize: 13 }}>
      <strong>{config.title || 'Embedded page'}</strong>
      <div>Conversation: {conversation ? conversation.id : '-'}</div>
    </div>
  )
}`

const REACT_CODE_PLACEHOLDER_CALL = `export default function App({ context, config, api }) {
  const call = context.call
  return (
    <div style={{ padding: 16, fontSize: 13 }}>
      <strong>{config.title || 'Screen pop page'}</strong>
      <div>Call record: {call ? call.recordId : '-'}</div>
      <div>Customer: {call ? call.customerNumber : '-'}</div>
    </div>
  )
}`

const PREVIEW_CONTEXT_CHAT: EmbeddedPageContext = {
  location: 'chat_auxiliary',
  agent: { id: 1, name: 'Agent Demo', email: 'agent@example.com' },
  conversation: { id: 1001, channelType: 'web', status: 'active' },
  visitor: { id: 501, name: 'Visitor Demo', email: 'visitor@example.com', phone: '13800000000', userId: 501 },
  call: null,
  user: { id: 501, name: 'Visitor Demo', phone: '13800000000' },
}

const PREVIEW_CONTEXT_CALL: EmbeddedPageContext = {
  location: 'call_screen_pop',
  agent: { id: 1, name: 'Agent Demo', email: 'agent@example.com' },
  conversation: null,
  visitor: null,
  call: {
    recordId: 9001,
    direction: 'inbound',
    customerNumber: '13800000000',
    queueId: 3,
    startedAt: '2026-08-07T10:00:00Z',
  },
  user: { id: 501, name: 'Visitor Demo', phone: '13800000000' },
}

function emptyContext(location: EmbeddedPageLocation): EmbeddedPageContext {
  return { location, agent: null, conversation: null, visitor: null, call: null, user: null }
}

type FormSnapshot = {
  name: string
  sortOrder: string
  pageType: EmbeddedPageType
  url: string
  reactCode: string
  configText: string
  enabled: boolean
  defaultFocus: boolean
}

function serializeSnapshot(input: FormSnapshot): string {
  return JSON.stringify(input)
}

const EMPTY_NEW_SNAPSHOT = serializeSnapshot({
  name: '',
  sortOrder: '0',
  pageType: 'iframe',
  url: '',
  reactCode: '',
  configText: '{}',
  enabled: false,
  defaultFocus: false,
})

function parseConfigText(text: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(text.trim() || '{}')
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
    return null
  } catch {
    return null
  }
}

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
      basicSetup={CODE_BASIC_SETUP}
      extensions={extensions}
      theme={CODE_THEME}
      indentWithTab
      className={`overflow-hidden rounded-lg border bg-[#0A0A0A] text-[13px] shadow-sm ${
        hasError ? 'border-destructive' : 'border-border'
      } [&_.cm-editor]:outline-none [&_.cm-focused]:outline-none [&_.cm-scroller]:font-mono [&_.cm-scroller]:leading-5`}
    />
  )
}

function FieldLabel({ label, required }: { label: string; required?: boolean }) {
  return (
    <div className="flex items-center gap-0.5">
      <span className="text-sm font-medium text-foreground">{label}</span>
      {required && <span className="text-sm font-medium text-destructive">*</span>}
    </div>
  )
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string
  description: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <div className="flex items-start justify-between gap-6 rounded-lg border border-border bg-card p-5">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-foreground">{label}</p>
        <p className="mt-1 text-sm leading-5 text-muted-foreground">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} aria-label={label} />
    </div>
  )
}

type EmbeddedPageFormProps = {
  pageId?: number
  location: EmbeddedPageLocation
  basePath: string
  backPath: string
}

export function EmbeddedPageForm({ pageId, location, basePath, backPath }: EmbeddedPageFormProps) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const isNew = pageId == null
  const isCall = location === 'call_screen_pop'
  const previewContext = isCall ? PREVIEW_CONTEXT_CALL : PREVIEW_CONTEXT_CHAT

  const { data: page, isPending: loadingPage, isError: loadError } = useEmbeddedPage(pageId ?? 0)
  const createMut = useCreateEmbeddedPage()
  const updateMut = useUpdateEmbeddedPage()

  const [initialized, setInitialized] = useState(isNew)
  const [savedSnapshot, setSavedSnapshot] = useState(EMPTY_NEW_SNAPSHOT)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const [name, setName] = useState('')
  const [sortOrder, setSortOrder] = useState('0')
  const [pageType, setPageType] = useState<EmbeddedPageType>('iframe')
  const [url, setUrl] = useState('')
  const [reactCode, setReactCode] = useState('')
  const [configText, setConfigText] = useState('{}')
  const [enabled, setEnabled] = useState(false)
  const [defaultFocus, setDefaultFocus] = useState(false)

  const [nameError, setNameError] = useState<string | null>(null)
  const [urlError, setUrlError] = useState<string | null>(null)
  const [codeError, setCodeError] = useState<string | null>(null)
  const [codeValid, setCodeValid] = useState(false)
  const [configError, setConfigError] = useState<string | null>(null)

  const [previewKey, setPreviewKey] = useState(0)
  const [previewVisible, setPreviewVisible] = useState(false)
  const [previewConfig, setPreviewConfig] = useState<Record<string, unknown>>({})
  const [previewRuntimeError, setPreviewRuntimeError] = useState<string | null>(null)

  useEffect(() => {
    if (page && !initialized) {
      const snapshot: FormSnapshot = {
        name: page.name,
        sortOrder: String(page.sort_order),
        pageType: page.page_type,
        url: page.url ?? '',
        reactCode: page.react_code ?? '',
        configText: JSON.stringify(page.config ?? {}, null, 2),
        enabled: page.enabled,
        defaultFocus: page.default_focus,
      }
      setName(snapshot.name)
      setSortOrder(snapshot.sortOrder)
      setPageType(snapshot.pageType)
      setUrl(snapshot.url)
      setReactCode(snapshot.reactCode)
      setConfigText(snapshot.configText)
      setEnabled(snapshot.enabled)
      setDefaultFocus(snapshot.defaultFocus)
      setSavedSnapshot(serializeSnapshot(snapshot))
      setInitialized(true)
    }
  }, [page, initialized])

  const currentSnapshot = useMemo(
    () =>
      serializeSnapshot({ name, sortOrder, pageType, url, reactCode, configText, enabled, defaultFocus }),
    [name, sortOrder, pageType, url, reactCode, configText, enabled, defaultFocus],
  )
  const isDirty = initialized && currentSnapshot !== savedSnapshot

  const showToast = (type: 'success' | 'error', text: string) => {
    setToast({ type, text })
    setTimeout(() => setToast(null), 3000)
  }

  const goBack = () => {
    if (isDirty && typeof window !== 'undefined' && !window.confirm(t('ep.form.leaveConfirm', locale))) {
      return
    }
    router.push(backPath)
  }

  const validateForm = (): boolean => {
    let ok = true
    const trimmedName = name.trim()
    if (!trimmedName) {
      setNameError(t('ep.form.name.required', locale))
      ok = false
    } else if (trimmedName.length > 40) {
      setNameError(t('ep.form.name.tooLong', locale))
      ok = false
    }

    if (pageType === 'iframe') {
      const trimmedUrl = url.trim()
      if (!trimmedUrl) {
        setUrlError(t('ep.form.url.required', locale))
        ok = false
      } else if (!/^https?:\/\//.test(trimmedUrl)) {
        setUrlError(t('ep.form.url.invalid', locale))
        ok = false
      } else if (trimmedUrl.length > 2000) {
        setUrlError(t('ep.form.url.tooLong', locale))
        ok = false
      }
    } else {
      if (!reactCode.trim()) {
        setCodeError(t('ep.form.code.required', locale))
        ok = false
      } else {
        const error = getAssistPanelCodeError(reactCode)
        if (error) {
          setCodeError(error)
          ok = false
        }
      }
    }

    if (parseConfigText(configText) === null) {
      setConfigError(t('ep.form.config.invalid', locale))
      ok = false
    }
    return ok
  }

  const handleSave = async () => {
    if (!validateForm()) return
    const payload: SaveEmbeddedPagePayload = {
      location,
      name: name.trim(),
      page_type: pageType,
      url: url.trim() || null,
      react_code: reactCode.trim() ? reactCode : null,
      config: parseConfigText(configText) ?? {},
      enabled,
      default_focus: defaultFocus,
      sort_order: Number.parseInt(sortOrder, 10) || 0,
    }
    try {
      if (isNew) {
        const created = await createMut.mutateAsync(payload)
        showToast(
          'success',
          created.default_focus_overridden
            ? t('ep.form.defaultFocusOverridden', locale)
            : t('ep.form.saveSuccess', locale),
        )
        router.replace(`${basePath}/${created.id}`)
      } else {
        const updated = await updateMut.mutateAsync({ id: pageId, data: payload })
        showToast(
          'success',
          updated.default_focus_overridden
            ? t('ep.form.defaultFocusOverridden', locale)
            : t('ep.form.saveSuccess', locale),
        )
        setSavedSnapshot(currentSnapshot)
      }
    } catch {
      showToast('error', t('ep.form.saveFailed', locale))
    }
  }

  const handleValidateCode = () => {
    setCodeValid(false)
    if (!reactCode.trim()) {
      setCodeError(t('ep.form.code.required', locale))
      return
    }
    const error = getAssistPanelCodeError(reactCode)
    setCodeError(error)
    setCodeValid(!error)
  }

  const handlePreview = () => {
    setPreviewRuntimeError(null)
    if (!reactCode.trim()) {
      setCodeError(t('ep.form.code.required', locale))
      setPreviewVisible(false)
      return
    }
    const error = getAssistPanelCodeError(reactCode)
    if (error) {
      setCodeError(error)
      setPreviewVisible(false)
      return
    }
    const parsed = parseConfigText(configText)
    if (parsed === null) {
      setConfigError(t('ep.form.config.invalid', locale))
      setPreviewVisible(false)
      return
    }
    setCodeError(null)
    setCodeValid(true)
    setPreviewConfig(parsed)
    setPreviewKey((key) => key + 1)
    setPreviewVisible(true)
  }

  const handleOpenInNewWindow = () => {
    const target = buildEmbeddedPageUrl(url.trim(), emptyContext(location))
    if (target) {
      window.open(target, '_blank', 'noopener,noreferrer')
    }
  }

  const previewApi = useMemo<EmbeddedPageApi>(
    () => ({
      getContext: () => previewContext,
      subscribeContext: (listener) => {
        listener(previewContext)
        return () => {}
      },
      openUrl: (target) => {
        window.open(target, '_blank', 'noopener,noreferrer')
      },
      navigate: () => {},
    }),
    [previewContext],
  )

  const saving = createMut.isPending || updateMut.isPending
  const saveDisabled = saving || !isDirty || !name.trim()

  if (!isNew && (loadingPage || !initialized)) {
    return <p className="p-8 text-sm text-muted-foreground">{t('ep.loading', locale)}</p>
  }
  if (!isNew && (loadError || !page)) {
    return <p className="p-8 text-sm text-destructive">{t('ep.form.loadFailed', locale)}</p>
  }

  const title = isNew ? t('ep.form.titleNew', locale) : t('ep.form.titleEdit', locale, { name: page?.name ?? '' })

  return (
    <div className="-m-8 flex flex-col">
      <div className="sticky -top-8 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <button type="button" onClick={goBack} className="flex items-center gap-2 text-left transition-colors">
          <IconArrowLeft size={20} className="text-muted-foreground" />
          <span className="text-base font-semibold text-foreground">{title}</span>
        </button>
        <button
          type="button"
          disabled={saveDisabled}
          onClick={handleSave}
          className="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-40"
        >
          {saving ? t('ep.form.saving', locale) : t('ep.form.save', locale)}
        </button>
      </div>

      {toast && (
        <div
          className={cn(
            'mx-8 mt-4 shrink-0 rounded-lg px-4 py-3 text-sm',
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700',
          )}
        >
          {toast.text}
        </div>
      )}

      <div className="flex w-[720px] flex-col gap-6 p-8">
        <section className="flex flex-col gap-4">
          <h2 className="border-b border-border pb-2 text-sm font-semibold text-foreground">
            {t('ep.form.section.basic', locale)}
          </h2>
          <div className="flex flex-col gap-2">
            <FieldLabel label={t('ep.form.name.label', locale)} required />
            <input
              value={name}
              onChange={(event) => {
                setName(event.target.value)
                setNameError(null)
              }}
              placeholder={t('ep.form.name.placeholder', locale)}
              className="h-10 w-full rounded-lg border border-border bg-white px-3.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            {nameError && <p className="text-xs text-destructive">{nameError}</p>}
          </div>
          <div className="flex flex-col gap-2">
            <FieldLabel label={t('ep.form.sortOrder.label', locale)} />
            <input
              value={sortOrder}
              onChange={(event) => setSortOrder(event.target.value)}
              type="number"
              step={1}
              className="h-10 w-[200px] rounded-lg border border-border bg-white px-3.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <p className="text-xs text-muted-foreground">{t('ep.form.sortOrder.help', locale)}</p>
          </div>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="border-b border-border pb-2 text-sm font-semibold text-foreground">
            {t('ep.form.section.source', locale)}
          </h2>
          <div className="flex flex-col gap-2">
            <FieldLabel label={t('ep.form.pageType.label', locale)} required />
            <div className="inline-flex w-fit rounded-lg border border-border bg-muted p-0.5">
              {(['iframe', 'react_code'] as const).map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setPageType(type)}
                  className={cn(
                    'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                    pageType === type ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground',
                  )}
                >
                  {t(`ep.form.pageType.${type}`, locale)}
                </button>
              ))}
            </div>
          </div>

          {pageType === 'iframe' ? (
            <>
              <div className="flex flex-col gap-2">
                <FieldLabel label={t('ep.form.url.label', locale)} required />
                <input
                  value={url}
                  onChange={(event) => {
                    setUrl(event.target.value)
                    setUrlError(null)
                  }}
                  placeholder={
                    isCall
                      ? t('ep.form.url.placeholderCall', locale)
                      : t('ep.form.url.placeholder', locale)
                  }
                  className="h-10 w-full rounded-lg border border-border bg-white px-3.5 font-mono text-[13px] text-foreground placeholder:font-sans placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                />
                {urlError && <p className="text-xs text-destructive">{urlError}</p>}
                <div>
                  <button
                    type="button"
                    onClick={handleOpenInNewWindow}
                    disabled={!url.trim()}
                    className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline disabled:opacity-40"
                  >
                    <IconExternalLink size={14} />
                    {t('ep.form.url.openInNewWindow', locale)}
                  </button>
                </div>
              </div>

              <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted/40 p-4">
                <p className="text-sm font-medium text-foreground">{t('ep.form.variables.title', locale)}</p>
                <div className="flex flex-wrap gap-1.5">
                  {EMBEDDED_PAGE_URL_VARIABLES_BY_LOCATION[location].map((variable) => (
                    <code
                      key={variable.key}
                      className="rounded-md border border-border bg-background px-1.5 py-0.5 font-mono text-[11px] text-foreground"
                    >
                      {variable.placeholder}
                    </code>
                  ))}
                </div>
                <p className="text-xs leading-5 text-muted-foreground">
                  {isCall
                    ? t('ep.form.variables.helpCall', locale)
                    : t('ep.form.variables.help', locale)}
                </p>
                <p className="text-xs leading-5 text-muted-foreground">
                  {t('ep.form.variables.postMessage', locale)}
                </p>
              </div>
            </>
          ) : (
            <>
              <div className="flex flex-col gap-2">
                <FieldLabel label={t('ep.form.code.label', locale)} required />
                <SourceCodeEditor
                  value={reactCode}
                  onChange={(value) => {
                    setReactCode(value)
                    setCodeError(null)
                    setCodeValid(false)
                    setPreviewVisible(false)
                  }}
                  placeholder={isCall ? REACT_CODE_PLACEHOLDER_CALL : REACT_CODE_PLACEHOLDER}
                  extensions={REACT_CODE_EXTENSIONS}
                  height="280px"
                  hasError={Boolean(codeError)}
                />
                {codeError ? (
                  <p className="text-xs text-destructive">{codeError}</p>
                ) : codeValid ? (
                  <p className="text-xs text-success">{t('ep.form.code.validateOk', locale)}</p>
                ) : null}
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={handleValidateCode}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-white px-4 text-sm font-medium text-foreground transition-colors hover:bg-accent"
                >
                  <IconPlayerPlay size={16} />
                  {t('ep.form.code.validate', locale)}
                </button>
                <button
                  type="button"
                  onClick={handlePreview}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-white px-4 text-sm font-medium text-foreground transition-colors hover:bg-accent"
                >
                  <IconEye size={16} />
                  {t('ep.form.code.preview', locale)}
                </button>
              </div>

              {previewVisible && (
                <div className="flex flex-col gap-2">
                  <p className="text-xs text-muted-foreground">{t('ep.form.code.previewTitle', locale)}</p>
                  <div className="h-[420px] overflow-hidden rounded-lg border border-border bg-white">
                    <EmbeddedPageRuntime
                      key={previewKey}
                      code={reactCode}
                      context={previewContext}
                      config={previewConfig}
                      api={previewApi}
                      onError={setPreviewRuntimeError}
                    />
                  </div>
                  {previewRuntimeError && <p className="text-xs text-destructive">{previewRuntimeError}</p>}
                </div>
              )}
            </>
          )}

          <div className="flex flex-col gap-2">
            <FieldLabel label={t('ep.form.config.label', locale)} />
            <SourceCodeEditor
              value={configText}
              onChange={(value) => {
                setConfigText(value)
                setConfigError(null)
              }}
              placeholder="{}"
              extensions={JSON_EXTENSIONS}
              height="140px"
              hasError={Boolean(configError)}
            />
            {configError ? (
              <p className="text-xs text-destructive">{configError}</p>
            ) : (
              <p className="text-xs leading-5 text-muted-foreground">{t('ep.form.config.help', locale)}</p>
            )}
          </div>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="border-b border-border pb-2 text-sm font-semibold text-foreground">
            {t('ep.form.section.display', locale)}
          </h2>
          <ToggleRow
            label={t('ep.form.enabled.label', locale)}
            description={
              isCall
                ? t('ep.form.enabled.descriptionCall', locale)
                : t('ep.form.enabled.description', locale)
            }
            checked={enabled}
            onChange={setEnabled}
          />
          <ToggleRow
            label={t('ep.form.defaultFocus.label', locale)}
            description={
              isCall
                ? t('ep.form.defaultFocus.descriptionCall', locale)
                : t('ep.form.defaultFocus.description', locale)
            }
            checked={defaultFocus}
            onChange={setDefaultFocus}
          />
        </section>
      </div>
    </div>
  )
}
