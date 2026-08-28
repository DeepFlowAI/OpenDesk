'use client'

import React from 'react'
import { compileAssistPanelComponent } from '@/app/components/features/visitor-chat/assist-panel-runtime'
import type { EmbeddedPageContext } from '@/models/embedded-page'

export type EmbeddedPageApi = {
  getContext: () => EmbeddedPageContext
  subscribeContext: (listener: (context: EmbeddedPageContext) => void) => () => void
  openUrl: (url: string) => void
  navigate: (path: string) => void
}

export type EmbeddedPageAppProps = {
  context: EmbeddedPageContext
  config: Record<string, unknown>
  api: EmbeddedPageApi
}

type EmbeddedPageRuntimeProps = {
  code: string
  context: EmbeddedPageContext
  config: Record<string, unknown>
  api: EmbeddedPageApi
  onError?: (message: string | null) => void
}

type BoundaryProps = {
  onError: (message: string) => void
  children: React.ReactNode
}

type BoundaryState = { error: Error | null }

class EmbeddedPageErrorBoundary extends React.Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error }
  }

  componentDidCatch(error: Error) {
    this.props.onError(error.message)
  }

  render() {
    if (this.state.error) return null
    return this.props.children
  }
}

function EmbeddedPageRuntimeInner({ code, context, config, api, onError }: EmbeddedPageRuntimeProps) {
  const compiled = React.useMemo(() => {
    if (!code.trim()) return { component: null, error: null }
    try {
      return { component: compileAssistPanelComponent<EmbeddedPageAppProps>(code), error: null }
    } catch (err) {
      return { component: null, error: err instanceof Error ? err.message : String(err) }
    }
  }, [code])

  React.useEffect(() => {
    onError?.(compiled.error)
  }, [compiled.error, onError])

  if (!compiled.component) return null
  const Component = compiled.component
  return <Component context={context} config={config} api={api} />
}

export function EmbeddedPageRuntime(props: EmbeddedPageRuntimeProps) {
  const handleError = React.useCallback(
    (message: string) => {
      props.onError?.(message)
    },
    [props.onError],
  )
  return (
    <EmbeddedPageErrorBoundary onError={handleError}>
      <EmbeddedPageRuntimeInner {...props} />
    </EmbeddedPageErrorBoundary>
  )
}
