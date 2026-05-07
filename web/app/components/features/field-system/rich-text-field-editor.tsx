'use client'

import { useEffect, type ReactNode } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Link from '@tiptap/extension-link'
import TurndownService from 'turndown'
import { marked } from 'marked'
import {
  IconBold,
  IconItalic,
  IconStrikethrough,
  IconList,
  IconListNumbers,
  IconQuote,
  IconSeparator,
  IconArrowBackUp,
  IconArrowForwardUp,
  IconLink,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

const turndown = new TurndownService({ headingStyle: 'atx' })

function markdownToHtml(src: string): string {
  if (!src.trim()) return ''
  const out = marked.parse(src, { async: false })
  return typeof out === 'string' ? out : ''
}

function normalizeEmpty(html: string): boolean {
  const t = html.replace(/\s|&nbsp;/g, '')
  return t === '' || t === '<p></p>' || t === '<p><br></p>'
}

export type RichTextFieldEditorProps = {
  value: unknown
  onChange: (v: string | null) => void
  typeConfig?: Record<string, unknown>
  placeholder?: string
  disabled?: boolean
  className?: string
  autoFocus?: boolean
  /** No outer border; white toolbar; single bottom border under toolbar. */
  plainChrome?: boolean
}

/**
 * Rich text field using Tiptap (https://tiptap.dev/).
 * Supports HTML or Markdown storage via typeConfig.rich_format.
 */
export function RichTextFieldEditor({
  value,
  onChange,
  typeConfig = {},
  placeholder = '',
  disabled = false,
  className,
  autoFocus = false,
  plainChrome = false,
}: RichTextFieldEditorProps) {
  const richFormat = ((typeConfig.rich_format as string) ?? 'html').toLowerCase()
  const isMarkdown = richFormat === 'markdown'

  const stringVal = value != null ? String(value) : ''
  const contentForEditor = !stringVal.trim()
    ? '<p></p>'
    : isMarkdown
      ? markdownToHtml(stringVal) || '<p></p>'
      : stringVal

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3] },
      }),
      Placeholder.configure({
        placeholder: placeholder || '…',
      }),
      Link.configure({
        openOnClick: false,
        autolink: true,
        defaultProtocol: 'https',
      }),
    ],
    content: contentForEditor,
    editable: !disabled,
    editorProps: {
      attributes: {
        class: cn(
          'prose prose-sm dark:prose-invert max-w-none min-h-[140px] px-3 py-2 outline-none',
          'prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1',
        ),
      },
    },
    onUpdate: ({ editor: ed }) => {
      const html = ed.getHTML()
      if (isMarkdown) {
        if (normalizeEmpty(html)) {
          onChange(null)
          return
        }
        const md = turndown.turndown(html)
        onChange(md || null)
      } else {
        if (normalizeEmpty(html)) {
          onChange(null)
          return
        }
        onChange(html)
      }
    },
  })

  useEffect(() => {
    if (!editor || editor.isDestroyed) return
    editor.setEditable(!disabled)
  }, [disabled, editor])

  useEffect(() => {
    if (!autoFocus || disabled || !editor || editor.isDestroyed) return
    editor.commands.focus('end')
  }, [autoFocus, disabled, editor])

  useEffect(() => {
    if (!editor || editor.isDestroyed) return
    const raw = value != null ? String(value) : ''
    const trimmed = raw.trim()
    const html = trimmed ? (isMarkdown ? markdownToHtml(raw) : raw) : ''
    const next = html || '<p></p>'
    const cur = editor.getHTML()

    if (!trimmed) {
      // Sync parent clear: isEmpty matches TipTap; getHTML() shape can fool normalizeEmpty.
      if (!editor.isEmpty) {
        editor.commands.setContent('<p></p>', { emitUpdate: false })
      }
      return
    }

    if (cur === next || (normalizeEmpty(cur) && normalizeEmpty(next))) return
    editor.commands.setContent(next, { emitUpdate: false })
  }, [value, editor, isMarkdown])

  if (!editor) {
    return (
      <div
        className={cn(
          'min-h-[180px] animate-pulse bg-muted/30',
          plainChrome ? 'rounded-none border-0' : 'rounded-md border border-border',
          className,
        )}
      />
    )
  }

  const runLink = () => {
    const prev = editor.getAttributes('link').href as string | undefined
    const url = window.prompt('URL', prev ?? 'https://')
    if (url === null) return
    if (url === '') {
      editor.chain().focus().extendMarkRange('link').unsetLink().run()
      return
    }
    editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
  }

  const toolbarIconSize = plainChrome ? 14 : 16

  return (
    <div
      className={cn(
        'overflow-hidden text-sm',
        plainChrome
          ? 'rounded-none border-0 bg-transparent focus-within:ring-0'
          : 'rounded-md border border-border bg-background focus-within:ring-1 focus-within:ring-ring',
        disabled && 'opacity-60',
        className,
      )}
    >
      <div
        className={cn(
          'flex flex-wrap items-center gap-0.5 border-b border-border',
          plainChrome ? 'bg-white px-0.5 py-0.5' : 'bg-muted/30 px-1 py-1',
        )}
      >
        <ToolbarBtn
          compact={plainChrome}
          disabled={disabled}
          active={editor.isActive('bold')}
          onClick={() => editor.chain().focus().toggleBold().run()}
          label="Bold"
        >
          <IconBold size={toolbarIconSize} />
        </ToolbarBtn>
        <ToolbarBtn
          compact={plainChrome}
          disabled={disabled}
          active={editor.isActive('italic')}
          onClick={() => editor.chain().focus().toggleItalic().run()}
          label="Italic"
        >
          <IconItalic size={toolbarIconSize} />
        </ToolbarBtn>
        <ToolbarBtn
          compact={plainChrome}
          disabled={disabled}
          active={editor.isActive('strike')}
          onClick={() => editor.chain().focus().toggleStrike().run()}
          label="Strike"
        >
          <IconStrikethrough size={toolbarIconSize} />
        </ToolbarBtn>
        <span
          className={cn('mx-0.5 w-px bg-border', plainChrome ? 'h-3' : 'h-4')}
          aria-hidden
        />
        <ToolbarBtn
          compact={plainChrome}
          disabled={disabled}
          active={editor.isActive('bulletList')}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          label="Bullet list"
        >
          <IconList size={toolbarIconSize} />
        </ToolbarBtn>
        <ToolbarBtn
          compact={plainChrome}
          disabled={disabled}
          active={editor.isActive('orderedList')}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          label="Ordered list"
        >
          <IconListNumbers size={toolbarIconSize} />
        </ToolbarBtn>
        <ToolbarBtn
          compact={plainChrome}
          disabled={disabled}
          active={editor.isActive('blockquote')}
          onClick={() => editor.chain().focus().toggleBlockquote().run()}
          label="Quote"
        >
          <IconQuote size={toolbarIconSize} />
        </ToolbarBtn>
        <ToolbarBtn
          compact={plainChrome}
          disabled={disabled}
          active={false}
          onClick={() => editor.chain().focus().setHorizontalRule().run()}
          label="Horizontal rule"
        >
          <IconSeparator size={toolbarIconSize} />
        </ToolbarBtn>
        <span
          className={cn('mx-0.5 w-px bg-border', plainChrome ? 'h-3' : 'h-4')}
          aria-hidden
        />
        <ToolbarBtn
          compact={plainChrome}
          disabled={disabled}
          active={editor.isActive('link')}
          onClick={runLink}
          label="Link"
        >
          <IconLink size={toolbarIconSize} />
        </ToolbarBtn>
        <span
          className={cn('mx-0.5 w-px bg-border', plainChrome ? 'h-3' : 'h-4')}
          aria-hidden
        />
        <ToolbarBtn
          compact={plainChrome}
          disabled={disabled || !editor.can().undo()}
          active={false}
          onClick={() => editor.chain().focus().undo().run()}
          label="Undo"
        >
          <IconArrowBackUp size={toolbarIconSize} />
        </ToolbarBtn>
        <ToolbarBtn
          compact={plainChrome}
          disabled={disabled || !editor.can().redo()}
          active={false}
          onClick={() => editor.chain().focus().redo().run()}
          label="Redo"
        >
          <IconArrowForwardUp size={toolbarIconSize} />
        </ToolbarBtn>
      </div>
      <EditorContent editor={editor} className="max-h-[min(360px,50vh)] overflow-y-auto" />
    </div>
  )
}

function ToolbarBtn({
  children,
  onClick,
  active,
  disabled,
  label,
  compact = false,
}: {
  children: ReactNode
  onClick: () => void
  active: boolean
  disabled?: boolean
  label: string
  compact?: boolean
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className={cn(
        compact ? 'h-7 w-7 shrink-0' : 'h-8 w-8 shrink-0',
        active && 'bg-muted text-foreground',
      )}
      disabled={disabled}
      onClick={onClick}
      aria-label={label}
      aria-pressed={active}
    >
      {children}
    </Button>
  )
}
