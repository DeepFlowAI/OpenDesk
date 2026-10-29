'use client'

import { useEffect, useRef, useState } from 'react'
import { IconCopy, IconRefresh, IconTrash } from '@tabler/icons-react'
import { HTTPError } from 'ky'
import { toast } from 'sonner'

import {
  CallEventTesterEvents,
  formatClockTime,
} from '@/app/components/features/call-center/call-event-tester-events'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { useLocaleStore } from '@/context/locale-store'
import { copyPlainTextToClipboard } from '@/lib/clipboard'
import { cn } from '@/lib/utils'
import {
  fetchOpenApi,
  requestEmbedSignature,
  resolveWebhookUrl,
  useCallEventTesterEvents,
  useCallEventTesterReceiver,
  useRotateCallEventTesterReceiver,
  useSetCallEventTesterSecret,
} from '@/service/use-call-event-tester'

interface OpenDeskCallInstance {
  ready: () => Promise<unknown>
  dial: (payload: Record<string, unknown>) => Promise<unknown>
  prefillDialer: (payload: Record<string, unknown>) => Promise<unknown>
  on: (name: string, callback: (payload: unknown, name: string) => void) => void
  destroy: () => void
}

declare global {
  interface Window {
    OpenDeskCall?: {
      create: (options: Record<string, unknown>) => OpenDeskCallInstance
    }
  }
}

const STORAGE_KEY = 'opendesk-call-event-tester'
const SDK_SILENCE_MS = 8000

interface TesterForm {
  integrationKey: string
  integrationSecret: string
  employeeIdentifier: string
  apiKey: string
  dialNumber: string
  dialContext: string
  dialInfo: string
}

const DEFAULT_FORM: TesterForm = {
  integrationKey: '',
  integrationSecret: '',
  employeeIdentifier: '',
  apiKey: '',
  dialNumber: '',
  dialContext:
    '{"record_type":"ticket","record_id":"T-1001","display_name":"Test ticket","attributes":{"source":"call-event-tester"}}',
  dialInfo: 'Business info from the call integration tester',
}

interface SdkLogLine {
  id: number
  at: string
  name: string
  payload: unknown
}

function loadForm(): TesterForm {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    return raw ? { ...DEFAULT_FORM, ...(JSON.parse(raw) as Partial<TesterForm>) } : DEFAULT_FORM
  } catch {
    return DEFAULT_FORM
  }
}

function loadSdkScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.OpenDeskCall) return resolve()
    const script = document.createElement('script')
    script.src = src
    script.onload = () => resolve()
    script.onerror = () => reject(new Error(`Failed to load ${src}`))
    document.head.appendChild(script)
  })
}

async function readError(error: unknown): Promise<{ code: string; message: string }> {
  if (error instanceof HTTPError) {
    try {
      const body = (await error.response.json()) as { code?: string; message?: string }
      return { code: body.code ?? String(error.response.status), message: body.message ?? error.message }
    } catch {
      return { code: String(error.response.status), message: error.message }
    }
  }
  return { code: 'ERROR', message: error instanceof Error ? error.message : String(error) }
}

function Section({ title, actions, children }: { title: string; actions?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border bg-background p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  )
}

function Field({ label, hint, children }: { label: string; hint?: React.ReactNode; children: React.ReactNode }) {
  return (
    <label className="mt-3 block first:mt-0">
      <span className="mb-1 flex items-center gap-1 text-xs font-medium text-muted-foreground">
        {label}
        {hint}
      </span>
      {children}
    </label>
  )
}

function StatusPill({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        'inline-flex h-6 items-center rounded-full border px-2.5 text-xs font-medium',
        ok
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-300'
          : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/15 dark:text-amber-300',
      )}
    >
      {children}
    </span>
  )
}

export function CallEventTester() {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const receiver = useCallEventTesterReceiver()
  const setSecret = useSetCallEventTesterSecret()
  const rotate = useRotateCallEventTesterReceiver()
  const { items: events, error: pollError, clear: clearEvents } = useCallEventTesterEvents(receiver.data?.token)

  const [form, setForm] = useState<TesterForm>(DEFAULT_FORM)
  const [subscriptionSecret, setSubscriptionSecret] = useState('')
  const [configMessage, setConfigMessage] = useState('')
  const [confirmRotate, setConfirmRotate] = useState(false)
  const [sdkStatus, setSdkStatus] = useState('')
  const [sdkLogs, setSdkLogs] = useState<SdkLogLine[]>([])
  const [recordingCallId, setRecordingCallId] = useState('')
  const [recordingResult, setRecordingResult] = useState('')
  const [origin, setOrigin] = useState('')
  const sdkRef = useRef<OpenDeskCallInstance | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const formRef = useRef(form)
  const logId = useRef(0)

  useEffect(() => {
    setForm(loadForm())
    setOrigin(window.location.origin)
    return () => sdkRef.current?.destroy()
  }, [])

  useEffect(() => {
    formRef.current = form
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(form))
  }, [form])

  const webhookUrl = receiver.data && origin ? resolveWebhookUrl(receiver.data.webhook_path) : ''
  const updateField = (key: keyof TesterForm) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }))

  const log = (name: string, payload: unknown) => {
    logId.current += 1
    const line = { id: logId.current, at: new Date().toISOString(), name, payload }
    setSdkLogs((prev) => [line, ...prev].slice(0, 200))
  }

  const copyWebhook = async () => {
    if (!webhookUrl) return
    const ok = await copyPlainTextToClipboard(webhookUrl)
    if (ok) toast.success(isZh ? '已复制' : 'Copied')
  }

  const saveConfig = async () => {
    const trimmed = Object.fromEntries(
      Object.entries(form).map(([key, value]) => [key, key.startsWith('dial') ? value : value.trim()]),
    ) as unknown as TesterForm
    const secret = subscriptionSecret.trim()
    const wrong: string[] = []
    if (secret && !secret.startsWith('odwhsec_')) wrong.push(isZh ? '订阅 Secret 应以 odwhsec_ 开头' : 'Subscription secret must start with odwhsec_')
    if (trimmed.integrationKey && (!trimmed.integrationKey.startsWith('ec_') || trimmed.integrationKey.startsWith('ecs_')))
      wrong.push(isZh ? '嵌入集成 Key 应以 ec_ 开头' : 'Integration key must start with ec_')
    if (trimmed.integrationSecret && !trimmed.integrationSecret.startsWith('ecs_'))
      wrong.push(isZh ? '嵌入集成密钥应以 ecs_ 开头' : 'Integration secret must start with ecs_')
    if (trimmed.apiKey && !trimmed.apiKey.startsWith('sk-odk-'))
      wrong.push(isZh ? 'API Key 应以 sk-odk- 开头' : 'API key must start with sk-odk-')
    if (wrong.length) {
      setConfigMessage(`${isZh ? '没有保存：' : 'Not saved: '}${wrong.join(isZh ? '；' : '; ')}`)
      return
    }
    setForm(trimmed)
    try {
      if (secret) {
        await setSecret.mutateAsync(secret)
        setSubscriptionSecret('')
      }
      setConfigMessage(
        isZh
          ? '已保存。改了集成配置的话，先点「销毁」再「加载组件」。'
          : 'Saved. If you changed the integration settings, destroy and reload the widget.',
      )
    } catch (error) {
      const { message } = await readError(error)
      setConfigMessage(`${isZh ? '保存失败：' : 'Save failed: '}${message}`)
    }
  }

  const clearSecret = async () => {
    await setSecret.mutateAsync(null)
    setConfigMessage(isZh ? '已清除订阅 Secret，接收器不再校验。' : 'Secret cleared; deliveries are no longer verified.')
  }

  const connectSdk = async () => {
    if (sdkRef.current || !containerRef.current) return
    const { integrationKey, integrationSecret, employeeIdentifier } = formRef.current
    if (!integrationKey || !integrationSecret || !employeeIdentifier) {
      setSdkStatus(
        isZh
          ? '请先填写并保存嵌入集成 Key、嵌入集成密钥和坐席用户名或邮箱。'
          : 'Fill in and save the integration key, integration secret and agent username first.',
      )
      return
    }
    setSdkStatus(isZh ? '加载 SDK 中…' : 'Loading SDK…')
    try {
      await loadSdkScript(`${window.location.origin}/sdk/opendesk-call.js`)
    } catch (error) {
      setSdkStatus(error instanceof Error ? error.message : String(error))
      return
    }
    const sdk = window.OpenDeskCall!.create({
      baseUrl: window.location.origin,
      integrationKey,
      container: containerRef.current,
      locale,
      getEmbedSignature: async ({ nonce, origin: hostOrigin }: { nonce: string; origin: string }) => {
        const current = formRef.current
        try {
          const result = await requestEmbedSignature({
            integrationKey: current.integrationKey,
            integrationSecret: current.integrationSecret,
            employeeIdentifier: current.employeeIdentifier,
            origin: hostOrigin,
            nonce,
          })
          log('[host] embed-signatures 200', { expires_in: result.expires_in })
          return result.embed_signature
        } catch (error) {
          const detail = await readError(error)
          log('[host] embed-signatures failed', detail)
          throw Object.assign(new Error(detail.message), { code: detail.code })
        }
      },
    })
    sdkRef.current = sdk
    let heardFromFrame = false
    sdk.on('*', (payload, name) => {
      heardFromFrame = true
      log(name, payload)
    })
    setSdkStatus(isZh ? '组件已创建，等待鉴权…' : 'Widget created, authenticating…')
    // A wrong key or disallowed origin blocks the frame without any message.
    window.setTimeout(() => {
      if (sdkRef.current === sdk && !heardFromFrame) {
        setSdkStatus(
          isZh
            ? `8 秒内没有收到组件消息：检查集成 Key 是否正确、集成是否启用、允许来源是否包含 ${window.location.origin}`
            : `No message from the widget within 8 seconds: check the integration key, that it is enabled, and that allowed origins include ${window.location.origin}`,
        )
      }
    }, SDK_SILENCE_MS)
    sdk
      .ready()
      .then(() => {
        if (sdkRef.current === sdk)
          setSdkStatus(
            isZh
              ? '组件已就绪。首次使用需在组件内点击「启用通话」授权麦克风。'
              : 'Widget ready. Click "Enable calling" inside the widget to grant microphone access.',
          )
      })
      .catch((error: { code?: string; message?: string }) => {
        if (sdkRef.current === sdk)
          setSdkStatus(`${isZh ? '组件鉴权失败：' : 'Authentication failed: '}${error.code ?? ''} ${error.message ?? ''}`)
      })
  }

  const destroySdk = () => {
    sdkRef.current?.destroy()
    sdkRef.current = null
    setSdkStatus(isZh ? '已销毁' : 'Destroyed')
  }

  const dialPayload = (): Record<string, unknown> | null => {
    const payload: Record<string, unknown> = { number: form.dialNumber.trim() }
    const context = form.dialContext.trim()
    if (context) {
      try {
        payload.externalContext = JSON.parse(context)
      } catch {
        toast.error(isZh ? 'externalContext 不是合法 JSON' : 'externalContext is not valid JSON')
        return null
      }
    }
    if (form.dialInfo.trim()) payload.customBusinessInfo = form.dialInfo
    return payload
  }

  const runSdkCommand = (command: 'dial' | 'prefillDialer') => {
    const sdk = sdkRef.current
    if (!sdk) {
      toast.error(isZh ? '先加载组件' : 'Load the widget first')
      return
    }
    const payload = dialPayload()
    if (!payload) return
    // dial must run synchronously inside the click handler: the SDK requires a user gesture.
    sdk[command](payload)
      .then((result) => log(`[host] ${command} ok`, result))
      .catch((error: { code?: string; message?: string }) =>
        log(`[host] ${command} error`, { code: error.code, message: error.message }),
      )
  }

  const callOpenApi = async (path: string) => {
    const apiKey = formRef.current.apiKey
    if (!apiKey) {
      setRecordingResult(isZh ? '请先填写并保存 API Key。' : 'Fill in and save the API key first.')
      return
    }
    setRecordingResult(isZh ? '查询中…' : 'Loading…')
    try {
      const result = await fetchOpenApi(apiKey, path)
      setRecordingResult(JSON.stringify(result, null, 2))
    } catch (error) {
      setRecordingResult((await readError(error)).message)
    }
  }

  const queryRecordings = (callId: string) => {
    setRecordingCallId(callId)
    void callOpenApi(`v1/open/call-center/calls/${encodeURIComponent(callId)}/recordings`)
  }

  const reissueRecording = (recordingId: string) => {
    void callOpenApi(`v1/open/call-center/recordings/${encodeURIComponent(recordingId)}/download-url`)
  }

  const hasSecret = Boolean(receiver.data?.has_secret)
  const hasApiKey = Boolean(form.apiKey)

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-muted/40">
      <header className="flex flex-wrap items-center gap-3 border-b border-border bg-background px-5 py-3">
        <h1 className="text-base font-semibold text-foreground">{isZh ? '通话集成测试台' : 'Call integration tester'}</h1>
        <StatusPill ok={hasSecret}>
          {hasSecret ? (isZh ? '校验订阅 Secret' : 'Verifying secret') : isZh ? '未配置订阅 Secret（不校验）' : 'No secret (not verified)'}
        </StatusPill>
        <StatusPill ok={hasApiKey}>
          {hasApiKey ? (isZh ? 'API Key 已填写' : 'API key set') : isZh ? '未填写 API Key' : 'No API key'}
        </StatusPill>
        <StatusPill ok={!pollError}>
          {pollError ? (isZh ? '事件拉取失败，重试中' : 'Polling failed, retrying') : isZh ? '事件接收中' : 'Receiving events'}
        </StatusPill>
        <div className="ml-auto flex min-w-0 items-center gap-2">
          <span className="text-xs text-muted-foreground">Webhook</span>
          <code className="max-w-[520px] truncate rounded-md bg-muted px-2 py-1 font-mono text-xs text-foreground">
            {webhookUrl || (isZh ? '生成中…' : 'Preparing…')}
          </code>
          <Button size="icon-sm" variant="outline" onClick={copyWebhook} disabled={!webhookUrl} aria-label={isZh ? '复制' : 'Copy'}>
            <IconCopy />
          </Button>
          <Button size="sm" variant="outline" onClick={() => setConfirmRotate(true)} disabled={!receiver.data}>
            <IconRefresh />
            {isZh ? '重置接收器' : 'Reset receiver'}
          </Button>
        </div>
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-[420px_minmax(0,1fr)] gap-4 overflow-hidden p-4">
        <div className="min-h-0 space-y-4 overflow-y-auto pr-1">
          <Section
            title={isZh ? '配置' : 'Configuration'}
            actions={
              <Button size="sm" onClick={saveConfig} disabled={setSecret.isPending}>
                {isZh ? '保存配置' : 'Save'}
              </Button>
            }
          >
            <div className="rounded-lg bg-muted/60 p-3 text-xs leading-relaxed text-muted-foreground">
              <p>{isZh ? '先在 OpenDesk 后台准备好下面三处，再把值填进来：' : 'Prepare these in OpenDesk first, then fill in the values:'}</p>
              <ol className="mt-1 list-decimal space-y-1 pl-4">
                <li>
                  {isZh ? '全局设置 > 事件订阅：新建订阅，Endpoint 填上方 Webhook 地址，记下 Secret' : 'Global settings > Event subscriptions: create one with the Webhook URL above and note the secret'}
                </li>
                <li>
                  {isZh ? '呼叫中心 > 通话集成 > 事件订阅：新建规则，选上面的订阅，勾选全部事件' : 'Call center > Integrations > Event subscriptions: create a rule for that subscription with all events'}
                </li>
                <li>
                  {isZh ? '呼叫中心 > 通话集成 > 嵌入式通话：新建集成，允许来源填 ' : 'Call center > Integrations > Embedded calling: create an integration allowing origin '}
                  <code className="font-mono text-foreground">{origin}</code>
                  {isZh ? '，记下集成 Key 和密钥' : ', and note its key and secret'}
                </li>
              </ol>
              <p className="mt-2">
                {isZh
                  ? '每人一个独立接收器，事件只有自己能看到；密钥只保存在当前标签页。多人同时测试时请各用各的坐席账号。'
                  : 'Each person gets a private receiver; secrets stay in this tab only. Use a different agent account per tester.'}
              </p>
            </div>
            <div className="mt-3">
              <Field
                label={isZh ? '订阅 Secret' : 'Subscription secret'}
                hint={
                  hasSecret ? (
                    <button type="button" className="ml-auto text-primary hover:underline" onClick={clearSecret}>
                      {isZh ? '清除' : 'Clear'}
                    </button>
                  ) : null
                }
              >
                <Input
                  type="password"
                  autoComplete="off"
                  value={subscriptionSecret}
                  onChange={(event) => setSubscriptionSecret(event.target.value)}
                  placeholder={hasSecret ? (isZh ? '已配置；留空表示不修改' : 'Configured; leave empty to keep') : (isZh ? 'odwhsec_ 开头' : 'Starts with odwhsec_')}
                />
              </Field>
              <Field label={isZh ? '嵌入集成 Key' : 'Integration key'}>
                <Input value={form.integrationKey} onChange={updateField('integrationKey')} placeholder={isZh ? 'ec_ 开头' : 'Starts with ec_'} />
              </Field>
              <Field label={isZh ? '嵌入集成密钥' : 'Integration secret'}>
                <Input type="password" autoComplete="off" value={form.integrationSecret} onChange={updateField('integrationSecret')} placeholder={isZh ? 'ecs_ 开头' : 'Starts with ecs_'} />
              </Field>
              <Field label={isZh ? '坐席用户名或邮箱' : 'Agent username or email'}>
                <Input value={form.employeeIdentifier} onChange={updateField('employeeIdentifier')} placeholder={isZh ? '登录 OpenDesk 用的用户名或邮箱' : 'The OpenDesk login username or email'} />
              </Field>
              <Field label={isZh ? 'API Key（录音开放接口）' : 'API key (recording open API)'}>
                <Input type="password" autoComplete="off" value={form.apiKey} onChange={updateField('apiKey')} placeholder={isZh ? 'sk-odk- 开头' : 'Starts with sk-odk-'} />
              </Field>
              {configMessage ? <p className="mt-3 text-xs text-muted-foreground">{configMessage}</p> : null}
            </div>
          </Section>

          <Section
            title={isZh ? '嵌入式通话组件' : 'Embedded call widget'}
            actions={
              <>
                <Button size="sm" onClick={connectSdk}>
                  {isZh ? '加载组件' : 'Load'}
                </Button>
                <Button size="sm" variant="outline" onClick={destroySdk}>
                  {isZh ? '销毁' : 'Destroy'}
                </Button>
              </>
            }
          >
            <p className="text-xs text-muted-foreground">
              {sdkStatus ||
                `${isZh ? '未加载。集成 Key：' : 'Not loaded. Key: '}${form.integrationKey || '-'} · ${isZh ? '坐席：' : 'Agent: '}${form.employeeIdentifier || '-'}`}
            </p>
            <div ref={containerRef} className="mt-3" />
          </Section>

          <Section title={isZh ? '外呼（通过 SDK dial）' : 'Outbound (SDK dial)'}>
            <Field label={isZh ? '被叫号码' : 'Number'}>
              <Input value={form.dialNumber} onChange={updateField('dialNumber')} placeholder={isZh ? '例如 13800000000' : 'e.g. 13800000000'} />
            </Field>
            <Field label={isZh ? 'externalContext（JSON，可空；所有事件都会回传）' : 'externalContext (JSON, optional; echoed in every event)'}>
              <Textarea rows={4} className="font-mono text-xs" value={form.dialContext} onChange={updateField('dialContext')} />
            </Field>
            <Field label={isZh ? 'customBusinessInfo（文本，可空；只在 call.ended 回传）' : 'customBusinessInfo (text, optional; only in call.ended)'}>
              <Textarea rows={2} value={form.dialInfo} onChange={updateField('dialInfo')} />
            </Field>
            <div className="mt-3 flex gap-2">
              <Button size="sm" onClick={() => runSdkCommand('dial')}>
                {isZh ? '拨打' : 'Dial'}
              </Button>
              <Button size="sm" variant="outline" onClick={() => runSdkCommand('prefillDialer')}>
                {isZh ? '只填入拨号盘' : 'Prefill dialer'}
              </Button>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              {isZh
                ? '呼入测试：组件就绪并置为可接听后，用手机拨打租户服务号码，在组件里接听即可。'
                : 'Inbound: once the widget is ready and available, call the tenant service number and answer in the widget.'}
            </p>
          </Section>

          <Section
            title={isZh ? 'SDK 浏览器事件' : 'SDK browser events'}
            actions={
              <Button size="sm" variant="outline" onClick={() => setSdkLogs([])}>
                {isZh ? '清空' : 'Clear'}
              </Button>
            }
          >
            <div className="max-h-64 space-y-1 overflow-y-auto font-mono text-[11px] leading-relaxed">
              {sdkLogs.length ? (
                sdkLogs.map((line) => (
                  <div key={line.id} className="break-all text-muted-foreground">
                    <span className="font-semibold text-foreground">
                      {formatClockTime(line.at, locale)} {line.name}
                    </span>{' '}
                    {JSON.stringify(line.payload)}
                  </div>
                ))
              ) : (
                <p className="text-muted-foreground">{isZh ? '暂无' : 'Nothing yet'}</p>
              )}
            </div>
          </Section>

          <Section title={isZh ? '录音开放接口' : 'Recording open API'}>
            <Field label={isZh ? '通话公开 ID（call public_id）' : 'Call public ID'}>
              <Input
                value={recordingCallId}
                onChange={(event) => setRecordingCallId(event.target.value)}
                placeholder={isZh ? '点通话卡片上的「查录音」会自动填入' : 'Filled when you click "Recordings" on a call'}
              />
            </Field>
            <div className="mt-3">
              <Button size="sm" variant="outline" onClick={() => recordingCallId.trim() && queryRecordings(recordingCallId.trim())}>
                {isZh ? '查询录音列表' : 'List recordings'}
              </Button>
            </div>
            {recordingResult ? (
              <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-100">
                {recordingResult}
              </pre>
            ) : null}
          </Section>
        </div>

        <section className="flex min-h-0 flex-col rounded-xl border border-border bg-background">
          <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold text-foreground">
              {isZh ? 'Webhook 事件（按通话分组，最新在上）' : 'Webhook events (grouped by call, newest first)'}
              {events.length ? (
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  {isZh ? `共 ${events.length} 条` : `${events.length} total`}
                </span>
              ) : null}
            </h2>
            <Button size="sm" variant="outline" onClick={() => void clearEvents()}>
              <IconTrash />
              {isZh ? '清空' : 'Clear'}
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {receiver.isError ? (
              <p className="text-sm text-destructive">{isZh ? '接收器创建失败，请刷新重试。' : 'Failed to create the receiver. Refresh to retry.'}</p>
            ) : (
              <CallEventTesterEvents
                events={events}
                isZh={isZh}
                locale={locale}
                onQueryRecordings={queryRecordings}
                onReissue={reissueRecording}
              />
            )}
          </div>
        </section>
      </main>

      <ConfirmDialog
        open={confirmRotate}
        title={isZh ? '重置接收器？' : 'Reset receiver?'}
        message={
          isZh
            ? '会生成新的 Webhook 地址并丢弃已收到的事件，需要把订阅的 Endpoint 改成新地址。'
            : 'A new Webhook URL is generated and received events are discarded. Update the subscription endpoint afterwards.'
        }
        confirmLabel={isZh ? '重置' : 'Reset'}
        cancelLabel={isZh ? '取消' : 'Cancel'}
        variant="destructive"
        loading={rotate.isPending}
        onCancel={() => setConfirmRotate(false)}
        onConfirm={async () => {
          await rotate.mutateAsync()
          setConfirmRotate(false)
          toast.success(isZh ? '已生成新地址' : 'New URL generated')
        }}
      />
    </div>
  )
}
