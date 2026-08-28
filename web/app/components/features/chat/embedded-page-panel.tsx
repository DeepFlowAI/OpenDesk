'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconLoader2 } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { EmbeddedPageRuntime, type EmbeddedPageApi } from '@/app/components/features/embedded-page-runtime'
import { buildEmbeddedPageUrl } from '@/utils/embedded-page'
import type { EmbeddedPageContext, EmbeddedPageWorkspaceItem } from '@/models/embedded-page'

const IFRAME_SANDBOX = 'allow-scripts allow-forms allow-same-origin allow-popups'
const VARIABLE_PATTERN = /\{[a-z_]+\}/

type Props = {
  page: EmbeddedPageWorkspaceItem
  context: EmbeddedPageContext
  hidden: boolean
}

export function EmbeddedPagePanel({ page, context, hidden }: Props) {
  return (
    <div className={cn('flex min-h-0 flex-1 flex-col bg-background', hidden && 'hidden')}>
      {page.page_type === 'iframe' ? (
        <IframeEmbeddedPage url={page.url ?? ''} context={context} />
      ) : (
        <ReactCodeEmbeddedPage code={page.react_code ?? ''} config={page.config} context={context} />
      )}
    </div>
  )
}

function IframeEmbeddedPage({ url, context }: { url: string; context: EmbeddedPageContext }) {
  const { locale } = useLocaleStore()
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const readyRef = useRef(false)
  const [retryKey, setRetryKey] = useState(0)
  const [loadError, setLoadError] = useState(false)

  const hasVariables = VARIABLE_PATTERN.test(url)
  const resolvedUrl = buildEmbeddedPageUrl(url, context)
  // URLs without variables stay on the first resolved src; updates go through postMessage only.
  const stableSrcRef = useRef(resolvedUrl)
  const src = hasVariables ? resolvedUrl : stableSrcRef.current

  const targetOrigin = useMemo(() => {
    try {
      return new URL(src).origin
    } catch {
      return null
    }
  }, [src])

  const contextRef = useRef(context)
  contextRef.current = context

  const postContext = useCallback(() => {
    const iframe = iframeRef.current
    if (!iframe?.contentWindow || !readyRef.current || !targetOrigin) return
    iframe.contentWindow.postMessage(
      { source: 'opendesk', type: 'context', payload: contextRef.current },
      targetOrigin,
    )
  }, [targetOrigin])

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const iframe = iframeRef.current
      if (!iframe?.contentWindow || event.source !== iframe.contentWindow) return
      const data = event.data as { source?: string; type?: string } | null
      if (data?.source === 'opendesk-embed' && data.type === 'ready') {
        readyRef.current = true
        postContext()
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [postContext])

  useEffect(() => {
    postContext()
  }, [context, postContext])

  if (loadError) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-5">
        <p className="text-sm text-muted-foreground">{t('ep.ws.loadFailed', locale)}</p>
        <button
          type="button"
          onClick={() => {
            setLoadError(false)
            readyRef.current = false
            setRetryKey((key) => key + 1)
          }}
          className="inline-flex h-8 items-center rounded-md border border-border px-3 text-xs font-medium text-foreground hover:bg-accent"
        >
          {t('ws.chat.retry', locale)}
        </button>
      </div>
    )
  }

  return (
    <iframe
      key={retryKey}
      ref={iframeRef}
      src={src}
      sandbox={IFRAME_SANDBOX}
      onError={() => setLoadError(true)}
      className="h-full w-full flex-1 border-0"
      title="embedded-page"
    />
  )
}

function ReactCodeEmbeddedPage({
  code,
  config,
  context,
}: {
  code: string
  config: Record<string, unknown>
  context: EmbeddedPageContext
}) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const [runtimeError, setRuntimeError] = useState<string | null>(null)

  const contextRef = useRef(context)
  contextRef.current = context
  const listenersRef = useRef(new Set<(context: EmbeddedPageContext) => void>())

  useEffect(() => {
    listenersRef.current.forEach((listener) => listener(context))
  }, [context])

  useEffect(() => {
    const listeners = listenersRef.current
    return () => listeners.clear()
  }, [])

  const api = useMemo<EmbeddedPageApi>(
    () => ({
      getContext: () => contextRef.current,
      subscribeContext: (listener) => {
        listenersRef.current.add(listener)
        listener(contextRef.current)
        return () => {
          listenersRef.current.delete(listener)
        }
      },
      openUrl: (target) => {
        window.open(target, '_blank', 'noopener,noreferrer')
      },
      navigate: (path) => {
        router.push(path)
      },
    }),
    [router],
  )

  if (runtimeError) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 px-5">
        <p className="text-sm text-muted-foreground">{t('ep.ws.runtimeFailed', locale)}</p>
        <p className="max-w-full truncate text-xs text-muted-foreground/70" title={runtimeError}>
          {runtimeError}
        </p>
      </div>
    )
  }

  if (!code.trim()) {
    return (
      <div className="flex flex-1 items-center justify-center px-5">
        <IconLoader2 size={18} className="animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <EmbeddedPageRuntime
        code={code}
        context={context}
        config={config}
        api={api}
        onError={setRuntimeError}
      />
    </div>
  )
}
