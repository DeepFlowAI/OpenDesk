'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft, IconCopy, IconCheck, IconLoader2, IconUpload, IconTrash } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { ChannelConfig, CreateChannelPayload } from '@/models/channel'
import { useChannel, useCreateChannel, useUpdateChannel } from '@/service/use-channels'
import { useServiceHours } from '@/service/use-service-hours'
import { useUploadChannelLogo, useUploadChannelFavicon } from '@/service/use-upload'
import { CHANNEL_COLOR_PREVIEW, channelColorPreview } from '@/utils/channel-config-display'
import { ChannelColorField } from '@/components/channel/channel-color-field'
import { Switch } from '@/components/ui/switch'
import { RichTextFieldEditor } from '@/app/components/features/field-system/rich-text-field-editor'

const DEFAULT_OFFLINE_TITLE = '当前客服不在线'
const DEFAULT_OFFLINE_MESSAGE = '您好，当前客服不在线，您可以稍后再来咨询，我们会尽快为您服务。'

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
  offline_title: DEFAULT_OFFLINE_TITLE,
  offline_message: DEFAULT_OFFLINE_MESSAGE,
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

function stripHtml(value: string): string {
  return value.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim()
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

function EmbedCodeSection({ channelId }: { channelId: number }) {
  const { locale } = useLocaleStore()
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  const snippet = `<script src="${origin}/sdk/opendesk.js"></script>\n<script>\n  OpenDesk.init({ channelId: ${channelId} });\n</script>`

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
  const createMut = useCreateChannel()
  const updateMut = useUpdateChannel()
  const logoUploadMut = useUploadChannelLogo()
  const faviconUploadMut = useUploadChannelFavicon()
  const logoFileRef = useRef<HTMLInputElement>(null)
  const faviconFileRef = useRef<HTMLInputElement>(null)

  const [name, setName] = useState('')
  const [accessMode, setAccessMode] = useState<'url' | 'embed'>('url')
  const [logoUrl, setLogoUrl] = useState('')
  const [logoError, setLogoError] = useState('')
  const [faviconUrl, setFaviconUrl] = useState('')
  const [faviconError, setFaviconError] = useState('')
  const [config, setConfig] = useState<ChannelConfig>({ ...DEFAULT_CONFIG })
  const [initialized, setInitialized] = useState(false)
  const [savedId, setSavedId] = useState<number | null>(channelId ?? null)
  const [activeTab, setActiveTab] = useState<'interface' | 'service'>('interface')
  const [serviceConfigError, setServiceConfigError] = useState('')
  const [offlineTitleError, setOfflineTitleError] = useState('')
  const [offlineMessageError, setOfflineMessageError] = useState('')

  useEffect(() => {
    if (isNew) { if (!initialized) setInitialized(true); return }
    if (!channel || initialized) return
    setName(channel.name)
    setAccessMode(channel.access_mode === 'embed' ? 'embed' : 'url')
    setLogoUrl(channel.logo_url ?? '')
    setFaviconUrl(channel.favicon_url ?? '')
    setConfig({ ...DEFAULT_CONFIG, ...channel.config })
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
        }),
      )
    }
  }, [isNew, channel, initialized])

  const currentSnapshot = useMemo(
    () => JSON.stringify({ name: name.trim(), access_mode: accessMode, logo_url: logoUrl.trim() || null, favicon_url: faviconUrl.trim() || null, config }),
    [name, accessMode, logoUrl, faviconUrl, config],
  )

  const emptySnapshot = JSON.stringify({ name: '', access_mode: 'url', logo_url: null, favicon_url: null, config: DEFAULT_CONFIG })
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

  const goBack = () => {
    if (isDirty && typeof window !== 'undefined' && !window.confirm(t('ch.form.leaveConfirm', locale))) return
    router.push('/channels/web')
  }

  const handleSave = async () => {
    const trimmed = name.trim()
    if (!trimmed || trimmed.length > 64) return
    setServiceConfigError('')
    setOfflineTitleError('')
    setOfflineMessageError('')
    if (config.service_hours_enabled && !config.service_hours_id) {
      setActiveTab('service')
      setServiceConfigError(t('ch.form.serviceHours.required', locale))
      return
    }
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
    const nextConfig = { ...config, offline_title: config.offline_title.trim() }
    const body: CreateChannelPayload = {
      name: trimmed,
      channel_type: 'web',
      access_mode: accessMode,
      logo_url: logoUrl.trim() || null,
      favicon_url: faviconUrl.trim() || null,
      config: nextConfig,
    }
    const snap = JSON.stringify({ name: trimmed, access_mode: accessMode, logo_url: body.logo_url ?? null, favicon_url: body.favicon_url ?? null, config: nextConfig })
    try {
      if (isNew || !savedId) {
        const created = await createMut.mutateAsync(body)
        setSavedId(created.id)
        setConfig(nextConfig)
        setSavedSnapshot(snap)
        router.replace(`/channels/web/${created.id}`)
      } else {
        await updateMut.mutateAsync({ id: savedId, data: body })
        setConfig(nextConfig)
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
        {/* Form — width 720, padding 24, gap 24 */}
        <div className="flex w-[720px] flex-col gap-6 p-6">
          <StandardTabSwitch
            options={[
              { value: 'interface' as const, label: t('ch.tab.interface', locale) },
              { value: 'service' as const, label: t('ch.tab.service', locale) },
            ]}
            value={activeTab}
            onChange={setActiveTab}
          />

          {activeTab === 'interface' && (
            <>
          {/* ── Section 0: Access Mode ── */}
          <SectionTitle>{t('ch.section.accessMode', locale)}</SectionTitle>
          <SegmentedControl
            options={[
              { value: 'url' as const, label: t('ch.accessMode.url', locale) },
              { value: 'embed' as const, label: t('ch.accessMode.embed', locale) },
            ]}
            value={accessMode}
            onChange={setAccessMode}
          />
          {savedId && (
            accessMode === 'url'
              ? <AccessLinkSection url={`${typeof window !== 'undefined' ? window.location.origin : ''}/chat/${savedId}`} />
              : <EmbedCodeSection channelId={savedId} />
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
        </div>
      </div>
    </div>
  )
}
