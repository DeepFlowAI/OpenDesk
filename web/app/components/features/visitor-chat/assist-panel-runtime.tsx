'use client'

import * as React from 'react'
import {
  Component,
  useMemo,
  type ErrorInfo,
  type ReactNode,
} from 'react'
import type { Locale } from '@/context/locale-store'
import type { AssistPanelConfigValue } from '@/models/channel'

export type AssistPanelStatus = {
  stage: 'initializing' | 'bot' | 'handoff_pending' | 'human' | 'ended' | 'offline'
  conversationStatus: string | null
  connectionStatus: 'connecting' | 'connected' | 'disconnected'
  botRunning: boolean
  handoffRouting: boolean
  canSendMessage: boolean
  canRequestHumanHandoff: boolean
  currentAgent: { id: number; name: string; avatar: string | null } | null
}

export type AssistPanelResult =
  | { ok: true }
  | { ok: false; code: string; message: string }

export type AssistPanelEventName =
  | 'status_changed'
  | 'agent_changed'
  | 'conversation_changed'
  | 'message_created'
  | 'context_changed'
  | 'panel_visibility_changed'

export type AssistPanelApi = {
  getChannel: () => Record<string, unknown>
  getConversation: () => Record<string, unknown>
  getCurrentStatus: () => AssistPanelStatus
  subscribeStatus: (listener: (next: AssistPanelStatus) => void) => () => void
  subscribeEvent: (eventName: AssistPanelEventName, listener: (payload: unknown) => void) => () => void
  getCurrentAgent: () => AssistPanelStatus['currentAgent']
  getVisitor: () => Record<string, unknown>
  getMessages: () => Record<string, unknown>[]
  sendMessage: (text: string) => Promise<AssistPanelResult>
  setComposerText: (text: string) => AssistPanelResult
  requestHumanHandoff: () => Promise<AssistPanelResult>
  openUrl: (url: string) => AssistPanelResult
}

type AssistAppProps = {
  api: AssistPanelApi
  status: AssistPanelStatus
  config: Record<string, AssistPanelConfigValue>
}

type AssistAppComponent = React.ComponentType<AssistAppProps>

const UNSUPPORTED_ASSIST_PANEL_PATTERNS = [
  /<\s*script\b/i,
  /\bimport\s*(?:\(|[^;\n]+from\b)/i,
  /\b(?:eval|fetch|XMLHttpRequest|WebSocket|EventSource|importScripts)\b/i,
  /\b(?:window|document|globalThis|localStorage|sessionStorage|indexedDB|navigator|location|parent|top|opener)\b/i,
  /\b(?:Function|constructor|__proto__|prototype)\b/,
]

function resultError(code: string, message: string): AssistPanelResult {
  return { ok: false, code, message }
}

export function validateAssistPanelCodeSource(code: string): boolean {
  return /\bexport\s+default\b/.test(code)
    && !UNSUPPORTED_ASSIST_PANEL_PATTERNS.some((pattern) => pattern.test(code))
}

function transformDefaultExport(source: string): string {
  const code = source.trim()
  if (/export\s+default\s+function\b/.test(code)) {
    return code.replace(/export\s+default\s+function\b/, 'return function')
  }
  if (/export\s+default\s+class\b/.test(code)) {
    return code.replace(/export\s+default\s+class\b/, 'return class')
  }

  const identifierExport = code.match(/export\s+default\s+([A-Za-z_$][\w$]*)\s*;?\s*$/)
  if (identifierExport) {
    return code.replace(/export\s+default\s+[A-Za-z_$][\w$]*\s*;?\s*$/, `return ${identifierExport[1]}`)
  }

  return code.replace(/\bexport\s+default\b/, 'return')
}

function compileAssistPanelComponent(source: string): AssistAppComponent {
  if (!validateAssistPanelCodeSource(source)) {
    throw new Error('Unsupported React code')
  }

  const transformed = transformDefaultExport(source)
  const factory = new Function(
    'React',
    'useState',
    'useEffect',
    'useMemo',
    'useCallback',
    'useRef',
    'Fragment',
    'window',
    'document',
    'globalThis',
    'localStorage',
    'sessionStorage',
    'indexedDB',
    'navigator',
    'location',
    'parent',
    'top',
    'opener',
    'fetch',
    'XMLHttpRequest',
    'WebSocket',
    'EventSource',
    'importScripts',
    `"use strict";\n${transformed}`,
  )
  const component = factory(
    React,
    React.useState,
    React.useEffect,
    React.useMemo,
    React.useCallback,
    React.useRef,
    React.Fragment,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
  ) as unknown

  if (typeof component !== 'function' && (typeof component !== 'object' || component === null)) {
    throw new Error('Default export must be a React component')
  }
  return component as AssistAppComponent
}

export function getAssistPanelCodeError(source: string): string | null {
  try {
    compileAssistPanelComponent(source)
    return null
  } catch (error) {
    return error instanceof Error ? error.message : 'Invalid React code'
  }
}

class AssistPanelErrorBoundary extends Component<
  { children: ReactNode; locale: Locale; resetKey: string },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(_error: Error, _errorInfo: ErrorInfo) {
    // Keep runtime errors inside the help panel.
  }

  componentDidUpdate(prevProps: { resetKey: string }) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null })
    }
  }

  render() {
    if (this.state.error) {
      return (
        <AssistPanelRuntimeError
          locale={this.props.locale}
          message={this.state.error.message}
        />
      )
    }
    return this.props.children
  }
}

function AssistPanelRuntimeError({ locale, message }: { locale: Locale; message: string }) {
  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-3 text-xs leading-5 text-destructive">
      <p className="font-medium">
        {locale === 'zh' ? '辅助信息加载失败' : 'Failed to load help content'}
      </p>
      <p className="mt-1 break-words text-destructive/80">{message}</p>
    </div>
  )
}

export function createAssistPanelError(code: string, message: string): AssistPanelResult {
  return resultError(code, message)
}

export function createAssistPanelOk(): AssistPanelResult {
  return { ok: true }
}

export function AssistPanelRuntime({
  code,
  api,
  status,
  config,
  locale,
}: {
  code: string
  api: AssistPanelApi
  status: AssistPanelStatus
  config: Record<string, AssistPanelConfigValue>
  locale: Locale
}) {
  const compiled = useMemo(() => {
    try {
      return { component: compileAssistPanelComponent(code), error: null as string | null }
    } catch (error) {
      return {
        component: null,
        error: error instanceof Error ? error.message : 'Invalid React code',
      }
    }
  }, [code])

  if (compiled.error || !compiled.component) {
    return (
      <AssistPanelRuntimeError
        locale={locale}
        message={compiled.error ?? 'Invalid React code'}
      />
    )
  }

  const AssistApp = compiled.component
  return (
    <AssistPanelErrorBoundary locale={locale} resetKey={code}>
      <AssistApp api={api} status={status} config={config} />
    </AssistPanelErrorBoundary>
  )
}
