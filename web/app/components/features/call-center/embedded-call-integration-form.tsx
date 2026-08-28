'use client'

import { useEffect, useState } from 'react'
import { IconArrowLeft, IconCheck, IconCopy, IconRefresh } from '@tabler/icons-react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import { EmbeddedCallOriginFields } from '@/app/components/features/call-center/embedded-call-origin-fields'
import { EmbeddedCallSecretDialog } from '@/app/components/features/call-center/embedded-call-secret-dialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Switch } from '@/components/ui/switch'
import { useLocaleStore } from '@/context/locale-store'
import { copyPlainTextToClipboard } from '@/lib/clipboard'
import {
  useCreateEmbeddedCallIntegration,
  useEmbeddedCallIntegration,
  useRevokePreviousEmbeddedCallSecret,
  useRotateEmbeddedCallSecret,
  useUpdateEmbeddedCallIntegration,
} from '@/service/use-embedded-call-integrations'

function pageOrigin() {
  return typeof window !== 'undefined' ? window.location.origin : ''
}

function buildHostPageSnippet(integrationKey: string, origin: string) {
  const sdkSrc = `${origin}/sdk/opendesk-call.js`
  return `<div id="opendesk-call"></div>
<script src="${sdkSrc}"></script>
<script>
  OpenDeskCall.create({
    integrationKey: ${JSON.stringify(integrationKey)},
    container: "#opendesk-call",
    getEmbedSignature: async ({ origin, nonce }) => {
      const response = await fetch("/your-backend/opendesk-call/signature", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ origin, nonce }),
      });
      if (!response.ok) throw new Error("Failed to issue embed signature");
      const data = await response.json();
      return data.embed_signature;
    },
  });
</script>`
}

function buildHostServerSnippet(integrationKey: string, origin: string) {
  return `POST ${origin}/api/v1/public/call-center/embed-signatures
X-OpenDesk-Integration-Secret: <server secret>

{
  "integration_key": ${JSON.stringify(integrationKey)},
  "employee_identifier": "<agent username or email>",
  "origin": "<from SDK>",
  "nonce": "<from SDK>"
}`
}

function formatDateTime(value: string | null, locale: string) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

export function EmbeddedCallIntegrationForm({ integrationId }: { integrationId: string | null }) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const detail = useEmbeddedCallIntegration(integrationId)
  const create = useCreateEmbeddedCallIntegration()
  const update = useUpdateEmbeddedCallIntegration()
  const rotate = useRotateEmbeddedCallSecret()
  const revokePrevious = useRevokePreviousEmbeddedCallSecret()
  const [name, setName] = useState('')
  const [origins, setOrigins] = useState([''])
  const [enabled, setEnabled] = useState(false)
  const [secret, setSecret] = useState<string | null>(null)
  const [createdIntegrationId, setCreatedIntegrationId] = useState<string | null>(null)
  const [confirmRotate, setConfirmRotate] = useState(false)
  const integration = detail.data
  const listPath = '/call-center/integrations/embedded-call'

  useEffect(() => {
    if (!integration) return
    setName(integration.name)
    setOrigins(integration.allowed_origins)
    setEnabled(integration.is_enabled)
  }, [integration])

  const pending = create.isPending || update.isPending
  const save = async () => {
    const allowedOrigins = origins
      .map((item) => item.trim().replace(/\/+$/, ''))
      .filter(Boolean)
    if (!name.trim() || allowedOrigins.length === 0) {
      toast.error(isZh ? '请填写名称和至少一个允许来源' : 'Enter a name and at least one allowed origin')
      return
    }
    try {
      if (integrationId) {
        await update.mutateAsync({
          id: integrationId,
          data: { name: name.trim(), allowed_origins: allowedOrigins, is_enabled: enabled },
        })
        toast.success(isZh ? '集成已保存' : 'Integration saved')
      } else {
        const result = await create.mutateAsync({
          name: name.trim(),
          allowed_origins: allowedOrigins,
          is_enabled: enabled,
        })
        setSecret(result.server_secret)
        setCreatedIntegrationId(result.integration.public_id)
      }
    } catch {
      toast.error(isZh ? '保存失败，请检查输入' : 'Save failed. Check your input.')
    }
  }

  const doRotate = async () => {
    if (!integrationId) return
    try {
      const result = await rotate.mutateAsync({ id: integrationId, gracePeriodHours: 24 })
      setSecret(result.server_secret)
      setConfirmRotate(false)
    } catch {
      toast.error(isZh ? '凭据轮换失败' : 'Failed to rotate credentials')
    }
  }

  const closeSecret = () => {
    setSecret(null)
    if (!createdIntegrationId) return
    router.replace(`${listPath}/${createdIntegrationId}`)
    setCreatedIntegrationId(null)
  }

  if (integrationId && detail.isLoading) {
    return <p className="text-sm text-muted-foreground">{isZh ? '加载中…' : 'Loading…'}</p>
  }
  if (integrationId && detail.isError) {
    return <p className="text-sm text-destructive">{isZh ? '集成不存在或加载失败' : 'Integration not found or failed to load'}</p>
  }

  return (
    <div className="-m-8 flex flex-col">
      <div className="sticky -top-8 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <button
          type="button"
          className="flex items-center gap-2 transition-colors hover:opacity-80"
          onClick={() => router.push(listPath)}
        >
          <IconArrowLeft size={20} className="text-muted-foreground" />
          <span className="text-base font-semibold text-foreground">
            {integrationId
              ? name || (isZh ? '编辑集成' : 'Edit integration')
              : isZh
                ? '新建集成'
                : 'New integration'}
          </span>
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={save}
          className="flex h-9 items-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
        >
          {pending ? (isZh ? '保存中…' : 'Saving…') : (isZh ? '保存' : 'Save')}
        </button>
      </div>

      <div className="flex w-[720px] max-w-full flex-col gap-6 p-8">
        <h3 className="text-base font-semibold text-foreground">{isZh ? '基本信息' : 'Basic information'}</h3>
        <div className="flex flex-col gap-2">
          <FieldLabel label={isZh ? '集成名称' : 'Integration name'} required />
          <input
            value={name}
            maxLength={50}
            onChange={(event) => setName(event.target.value)}
            placeholder={isZh ? '用于识别第三方系统' : 'Identifies the host application'}
            className="h-10 w-full rounded-lg border border-border bg-white px-3.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <div className="flex items-center justify-between gap-6">
          <div>
            <p className="text-sm font-medium text-foreground">{isZh ? '启用集成' : 'Enable integration'}</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {isZh
                ? '关闭后停止签发新会话，进行中通话可自然结束。'
                : 'Disabling blocks new sessions while active calls can finish.'}
            </p>
          </div>
          <Switch checked={enabled} onCheckedChange={setEnabled} />
        </div>

        <Separator />

        <h3 className="text-base font-semibold text-foreground">{isZh ? '安全来源' : 'Allowed origins'}</h3>
        <div className="flex flex-col gap-2">
          <FieldLabel label={isZh ? '允许 Origin' : 'Origins'} required />
          <p className="text-xs leading-5 text-muted-foreground">
            {isZh
              ? '只允许精确 HTTPS Origin，不支持路径或通配符。从浏览器复制时末尾的 / 会自动去掉。'
              : 'Exact HTTPS origins only. Paths and wildcards are rejected. A trailing slash from a copied URL is stripped.'}
          </p>
          <EmbeddedCallOriginFields values={origins} disabled={pending} isZh={isZh} onChange={setOrigins} />
        </div>

        {integration && (
          <>
            <Separator />
            <h3 className="text-base font-semibold text-foreground">{isZh ? '服务端凭据' : 'Server credentials'}</h3>
            <CopyField
              label="Integration key"
              value={integration.integration_key}
              hint={isZh ? '可放在宿主前端，不代表认证。' : 'Safe to store in the host frontend. It is not a credential.'}
              isZh={isZh}
            />
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-foreground">Server secret</p>
                <p className="mt-1 font-mono text-xs text-muted-foreground">•••• •••• {integration.secret_last_four}</p>
              </div>
              <button
                type="button"
                disabled={rotate.isPending}
                onClick={() => setConfirmRotate(true)}
                className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-border px-3 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent disabled:opacity-50"
              >
                <IconRefresh size={16} />
                {isZh ? '轮换 Secret' : 'Rotate secret'}
              </button>
            </div>
            {integration.previous_secret_expires_at && (
              <button
                type="button"
                disabled={revokePrevious.isPending}
                onClick={() => integrationId && revokePrevious.mutate(integrationId)}
                className="h-9 w-fit rounded-lg border border-destructive px-3 text-sm font-medium text-destructive transition-colors hover:bg-destructive/5 disabled:opacity-50"
              >
                {isZh ? '提前结束旧 Secret' : 'Revoke previous secret now'}
              </button>
            )}
          </>
        )}

        {integration ? (
          <>
            <Separator />
            <h3 className="text-base font-semibold text-foreground">SDK</h3>
            <CopyField
              label={isZh ? '页面接入' : 'Host page'}
              value={buildHostPageSnippet(integration.integration_key, pageOrigin())}
              hint={isZh
                ? '把这段放到第三方页面。/your-backend/opendesk-call/signature 需换成你们自己的接口，不要把 Server secret 写进浏览器。'
                : 'Paste this into the host page. Replace /your-backend/opendesk-call/signature with your own API. Never put the server secret in the browser.'}
              isZh={isZh}
              multiline
            />
            <CopyField
              label={isZh ? '服务端签发签名' : 'Host server'}
              value={buildHostServerSnippet(integration.integration_key, pageOrigin())}
              hint={isZh
                ? '由你们的服务端调用。employee_identifier 用当前登录坐席的用户名或邮箱；origin 和 nonce 原样转发 SDK 传入的值。'
                : 'Call this from your server. employee_identifier is the signed-in agent username or email. Forward origin and nonce from the SDK unchanged.'}
              isZh={isZh}
              multiline
            />
          </>
        ) : (
          <>
            <Separator />
            <h3 className="text-base font-semibold text-foreground">SDK</h3>
            <p className="text-sm text-muted-foreground">
              {isZh ? '保存集成后会生成带 Integration key 的接入示例。' : 'A copyable snippet with the integration key appears after you save.'}
            </p>
          </>
        )}

        {integration && (
          <>
            <Separator />
            <h3 className="text-base font-semibold text-foreground">{isZh ? '连接诊断' : 'Connection diagnostics'}</h3>
            <dl className="grid grid-cols-[120px_minmax(0,1fr)] gap-x-4 gap-y-3 text-sm">
              <dt className="text-muted-foreground">{isZh ? '最近成功' : 'Last success'}</dt>
              <dd>{formatDateTime(integration.last_success_at, locale)}</dd>
              <dt className="text-muted-foreground">{isZh ? '最近失败' : 'Last failure'}</dt>
              <dd>{formatDateTime(integration.last_failure_at, locale)}</dd>
              <dt className="text-muted-foreground">{isZh ? '错误类型' : 'Error code'}</dt>
              <dd className="break-all font-mono text-xs">{integration.last_error_code || '—'}</dd>
            </dl>
          </>
        )}
      </div>

      <ConfirmDialog
        open={confirmRotate}
        title={isZh ? '轮换集成凭据' : 'Rotate integration secret'}
        message={isZh ? '新凭据生成后，请在 24 小时过渡期内更新第三方服务端。' : 'Update the host server during the 24-hour transition window.'}
        itemName={integration?.name}
        confirmLabel={isZh ? '确认轮换' : 'Rotate'}
        cancelLabel={isZh ? '取消' : 'Cancel'}
        loading={rotate.isPending}
        onCancel={() => setConfirmRotate(false)}
        onConfirm={doRotate}
      />
      <EmbeddedCallSecretDialog open={secret !== null} secret={secret} isZh={isZh} onClose={closeSecret} />
    </div>
  )
}

function FieldLabel({ label, required }: { label: string; required?: boolean }) {
  return (
    <div className="flex items-center gap-0.5">
      <span className="text-sm font-medium text-foreground">{label}</span>
      {required ? <span className="text-sm font-medium text-destructive">*</span> : null}
    </div>
  )
}

function Separator() {
  return <div className="h-px w-full bg-border" />
}

function CopyField({
  label,
  value,
  hint,
  isZh,
  multiline = false,
}: {
  label: string
  value: string
  hint: string
  isZh: boolean
  multiline?: boolean
}) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    const ok = await copyPlainTextToClipboard(value)
    if (!ok) {
      toast.error(isZh ? '复制失败' : 'Failed to copy')
      return
    }
    setCopied(true)
    toast.success(isZh ? '已复制' : 'Copied')
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm font-medium text-foreground">{label}</p>
      <div className="flex items-start gap-3">
        {multiline ? (
          <pre className="min-w-0 flex-1 overflow-x-auto whitespace-pre-wrap rounded-lg bg-accent px-3.5 py-2.5 font-mono text-[13px] text-foreground/80">
            {value}
          </pre>
        ) : (
          <code className="min-w-0 flex-1 truncate rounded-lg bg-accent px-3.5 py-2.5 font-mono text-[13px] text-foreground/80">
            {value}
          </code>
        )}
        <button
          type="button"
          onClick={copy}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-border px-4 text-[13px] font-medium text-foreground/80 transition-colors hover:bg-accent"
        >
          {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
          {copied ? (isZh ? '已复制' : 'Copied') : (isZh ? '复制' : 'Copy')}
        </button>
      </div>
      <p className="text-xs leading-5 text-muted-foreground">{hint}</p>
    </div>
  )
}
