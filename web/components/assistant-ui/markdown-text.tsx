'use client'

import { MarkdownTextPrimitive } from '@assistant-ui/react-markdown'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'

const markdownRemarkPlugins = [remarkGfm]
export const markdownTextRootClass = [
  'whitespace-normal break-words leading-7 [overflow-wrap:anywhere]',
  '[&>*:first-child]:mt-0 [&>*:last-child]:mb-0',
].join(' ')

const markdownComponents: Components = {
  p: ({ node: _node, className, ...props }) => (
    <p className={cn('my-1 leading-7 first:mt-0 last:mb-0', className)} {...props} />
  ),
  h1: ({ node: _node, className, ...props }) => (
    <h1 className={cn('mb-2 mt-3 text-2xl font-semibold leading-tight first:mt-0', className)} {...props} />
  ),
  h2: ({ node: _node, className, ...props }) => (
    <h2 className={cn('mb-2 mt-3 text-xl font-semibold leading-tight first:mt-0', className)} {...props} />
  ),
  h3: ({ node: _node, className, ...props }) => (
    <h3 className={cn('mb-1.5 mt-2.5 text-lg font-semibold leading-snug first:mt-0', className)} {...props} />
  ),
  h4: ({ node: _node, className, ...props }) => (
    <h4 className={cn('mb-1 mt-2 text-base font-semibold first:mt-0', className)} {...props} />
  ),
  h5: ({ node: _node, className, ...props }) => (
    <h5 className={cn('mb-1 mt-2 text-sm font-semibold first:mt-0', className)} {...props} />
  ),
  h6: ({ node: _node, className, ...props }) => (
    <h6 className={cn('mb-1 mt-2 text-xs font-semibold first:mt-0', className)} {...props} />
  ),
  ul: ({ node: _node, className, ...props }) => (
    <ul className={cn('my-1 list-disc space-y-1.5 ps-5 first:mt-0 last:mb-0', className)} {...props} />
  ),
  ol: ({ node: _node, className, ...props }) => (
    <ol className={cn('my-1 list-decimal space-y-1.5 ps-5 first:mt-0 last:mb-0', className)} {...props} />
  ),
  li: ({ node: _node, className, ...props }) => (
    <li className={cn('my-0.5 leading-7 [&>p]:my-0', className)} {...props} />
  ),
  blockquote: ({ node: _node, className, ...props }) => (
    <blockquote
      className={cn('my-2 border-l-4 border-border pl-3 italic text-muted-foreground [&_p]:my-0', className)}
      {...props}
    />
  ),
  hr: ({ node: _node, className, ...props }) => (
    <hr className={cn('my-3 border-border', className)} {...props} />
  ),
  table: ({ node: _node, className, ...props }) => (
    <div className="my-3 max-w-full overflow-x-auto">
      <table
        className={cn('w-max min-w-max border-collapse text-left text-sm leading-7 text-[#111827]', className)}
        {...props}
      />
    </div>
  ),
  thead: ({ node: _node, className, ...props }) => (
    <thead className={cn('bg-white', className)} {...props} />
  ),
  tr: ({ node: _node, className, ...props }) => (
    <tr className={cn('even:bg-[#F8FAFC]', className)} {...props} />
  ),
  th: ({ node: _node, className, ...props }) => (
    <th
      className={cn('border border-[#CBD5E1] bg-white px-4 py-3 text-center align-middle font-semibold text-[#111827]', className)}
      {...props}
    />
  ),
  td: ({ node: _node, className, ...props }) => (
    <td
      className={cn('border border-[#CBD5E1] px-4 py-3 align-middle', className)}
      {...props}
    />
  ),
  a: ({ node: _node, className, ...props }) => (
    <a className={cn('text-primary underline underline-offset-2', className)} {...props} />
  ),
  code: ({ node: _node, className, ...props }) => (
    <code
      className={cn('rounded-sm bg-muted px-1 py-0.5 font-mono text-[0.9em]', className)}
      {...props}
    />
  ),
  pre: ({ node: _node, className, ...props }) => (
    <pre className={cn('my-2 overflow-x-auto rounded-md bg-muted p-2 text-xs leading-6', className)} {...props} />
  ),
}

export function AssistantMarkdownText() {
  return (
    <MarkdownTextPrimitive
      components={markdownComponents}
      remarkPlugins={markdownRemarkPlugins}
    />
  )
}

export function MarkdownText({ children }: { children: string }) {
  return (
    <ReactMarkdown
      components={markdownComponents}
      remarkPlugins={markdownRemarkPlugins}
    >
      {children}
    </ReactMarkdown>
  )
}
