'use client'

import { useCallback, useLayoutEffect, useRef, type UIEvent } from 'react'

const DEFAULT_BOTTOM_THRESHOLD = 80

function isNearBottom(element: HTMLElement, threshold: number): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight < threshold
}

export function useBottomScrollAnchor<T extends HTMLElement>(
  anchorKey: unknown,
  threshold = DEFAULT_BOTTOM_THRESHOLD,
) {
  const scrollRef = useRef<T | null>(null)
  const shouldStickToBottomRef = useRef(true)
  const frameRef = useRef<number | null>(null)

  const scrollToBottom = useCallback(() => {
    const element = scrollRef.current
    if (!element) return
    element.scrollTop = element.scrollHeight
  }, [])

  const scheduleScrollToBottom = useCallback(() => {
    if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current)
    frameRef.current = window.requestAnimationFrame(() => {
      frameRef.current = null
      scrollToBottom()
    })
  }, [scrollToBottom])

  const onScroll = useCallback((event: UIEvent<T>) => {
    shouldStickToBottomRef.current = isNearBottom(event.currentTarget, threshold)
  }, [threshold])

  useLayoutEffect(() => {
    if (shouldStickToBottomRef.current) scheduleScrollToBottom()
  }, [anchorKey, scheduleScrollToBottom])

  useLayoutEffect(() => {
    const element = scrollRef.current
    if (!element || typeof ResizeObserver === 'undefined') return

    const observer = new ResizeObserver(() => {
      if (shouldStickToBottomRef.current) scheduleScrollToBottom()
    })
    observer.observe(element)

    return () => observer.disconnect()
  }, [scheduleScrollToBottom])

  useLayoutEffect(() => {
    return () => {
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current)
    }
  }, [])

  return { scrollRef, onScroll }
}
