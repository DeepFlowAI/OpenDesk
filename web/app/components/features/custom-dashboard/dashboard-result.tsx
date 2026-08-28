'use client'

import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import ReactMarkdown from 'react-markdown'

function EChartsResult({ option }: { option: Record<string, unknown> }) {
  const elementRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!elementRef.current) return
    const chart = echarts.init(elementRef.current)
    chart.setOption(option as EChartsOption)
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(elementRef.current)
    return () => { observer.disconnect(); chart.dispose() }
  }, [option])
  return <div ref={elementRef} className="h-full min-h-40 w-full" role="img" aria-label="Chart" />
}

export function DashboardResult({ output }: { output: Record<string, unknown> }) {
  if (output.type === 'metric') {
    return (
      <div className="flex h-full flex-col justify-center p-5">
        <span className="text-3xl font-semibold tabular-nums text-foreground">{String(output.value ?? '—')}</span>
        <span className="mt-2 text-sm text-muted-foreground">{String(output.label ?? '')}</span>
      </div>
    )
  }
  if (output.type === 'echarts' && output.option && typeof output.option === 'object') {
    return <EChartsResult option={output.option as Record<string, unknown>} />
  }
  if (output.type === 'table' && Array.isArray(output.columns) && Array.isArray(output.rows)) {
    const columns = output.columns.map((column) => typeof column === 'string' ? { key: column, label: column } : column as { key?: string; label?: string; name?: string })
    return (
      <div className="h-full overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-muted"><tr>{columns.map((column, index) => <th key={column.key ?? index} className="px-3 py-2 font-medium">{column.label ?? column.name ?? column.key}</th>)}</tr></thead>
          <tbody>{(output.rows as unknown[]).map((row, rowIndex) => <tr key={rowIndex} className="border-t border-border">{columns.map((column, columnIndex) => <td key={column.key ?? columnIndex} className="px-3 py-2">{String(Array.isArray(row) ? row[columnIndex] ?? '' : (row as Record<string, unknown>)[column.key ?? ''] ?? '')}</td>)}</tr>)}</tbody>
        </table>
      </div>
    )
  }
  if (output.type === 'markdown' && typeof output.content === 'string') {
    return <div className="prose prose-sm max-w-none overflow-auto p-4 text-foreground"><ReactMarkdown skipHtml components={{ a: ({ children }) => <span>{children}</span> }}>{output.content}</ReactMarkdown></div>
  }
  return null
}
