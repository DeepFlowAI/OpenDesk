import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { OpenAgentTraceBlocks } from './open-agent-trace-blocks'

const thinkingBlocks = [
  {
    id: 'think-1',
    content: 'user is asking about features',
    llmStepId: 1,
    isStreaming: false,
    timelineIndex: 1,
  },
  {
    id: 'think-2',
    content: 'let me summarize the products',
    llmStepId: 2,
    isStreaming: false,
    timelineIndex: 4,
  },
]

const toolBlocks = [
  {
    id: 'tool-1',
    toolName: 'search',
    brief: '检索 OpenAgent 核心功能',
    toolCallId: 'call-1',
    stepId: 11,
    isExecuting: false,
    timelineIndex: 2,
  },
  {
    id: 'tool-2',
    toolName: 'search',
    brief: '检索 OpenDesk 核心功能',
    toolCallId: 'call-2',
    stepId: 12,
    isExecuting: false,
    timelineIndex: 3,
  },
]

const textBlocks = [
  {
    id: 'text-1',
    content: '我们主要提供两款产品',
    isStreaming: false,
    timelineIndex: 5,
  },
]

describe('OpenAgentTraceBlocks process collapse', () => {
  it('collapses completed thinking and tools behind a summary', () => {
    const html = renderToStaticMarkup(createElement(OpenAgentTraceBlocks, {
      textBlocks,
      thinkingBlocks,
      toolBlocks,
      locale: 'zh',
    }))

    expect(html).toContain('data-open-agent-process')
    expect(html).toContain('已思考')
    expect(html).toContain('调用了 2 个工具')
    expect(html).toContain('我们主要提供两款产品')
    expect(html).not.toContain('data-open-agent-thinking')
    expect(html).not.toContain('user is asking about features')
    expect(html).not.toContain('检索 OpenAgent 核心功能')
    expect(html).not.toContain('data-open-agent-process-open')
    expect(html).toContain('w-0')
    expect(html).toContain('min-w-full')
  })

  it('expands the process while streaming but keeps finished thoughts collapsed', () => {
    const html = renderToStaticMarkup(createElement(OpenAgentTraceBlocks, {
      textBlocks,
      thinkingBlocks,
      toolBlocks,
      locale: 'zh',
      isStreaming: true,
    }))

    expect(html).toContain('data-open-agent-process-open')
    expect(html).toContain('data-open-agent-thinking')
    expect(html).toContain('检索 OpenAgent 核心功能')
    expect(html).not.toContain('user is asking about features')
    expect(html).not.toContain('已思考')
  })

  it('expands the summary on click without revealing finished thought text', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    await act(async () => {
      root.render(createElement(OpenAgentTraceBlocks, {
        textBlocks,
        thinkingBlocks,
        toolBlocks,
        locale: 'zh',
      }))
    })

    expect(container.querySelector('[data-open-agent-thinking]')).toBeNull()

    await act(async () => {
      container.querySelector<HTMLButtonElement>('[data-open-agent-process]')?.click()
    })

    expect(container.querySelector('[data-open-agent-process-open]')).not.toBeNull()
    expect(container.querySelectorAll('[data-open-agent-thinking]')).toHaveLength(2)
    expect(container.textContent).toContain('检索 OpenDesk 核心功能')
    expect(container.textContent).not.toContain('user is asking about features')
    expect(container.querySelector('[data-open-agent-process-open]')?.className).toContain('w-0')
    expect(container.querySelector('[data-open-agent-process-open]')?.className).toContain('min-w-full')

    await act(async () => root.unmount())
    container.remove()
  })

  it('does not lock process width when there is no answer content yet', () => {
    const html = renderToStaticMarkup(createElement(OpenAgentTraceBlocks, {
      textBlocks: [],
      thinkingBlocks,
      toolBlocks,
      locale: 'zh',
      isStreaming: true,
    }))

    expect(html).toContain('data-open-agent-process-open')
    expect(html).not.toContain('w-0 min-w-full')
  })
})
