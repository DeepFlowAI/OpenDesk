'use client'

import { useEffect, useRef, useState } from 'react'
import { useEditor, EditorContent, type Editor } from '@tiptap/react'
import { Node, mergeAttributes } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Link from '@tiptap/extension-link'
import Highlight from '@tiptap/extension-highlight'
import TurndownService from 'turndown'
import { marked } from 'marked'
import { cn } from '@/lib/utils'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { useUploadCustomFieldFile } from '@/service/use-upload'
import { BlockquoteButton } from '@/components/tiptap-ui/blockquote-button'
import { ColorHighlightPopover } from '@/components/tiptap-ui/color-highlight-popover'
import { HeadingDropdownMenu } from '@/components/tiptap-ui/heading-dropdown-menu'
import { LinkPopover } from '@/components/tiptap-ui/link-popover'
import { ListDropdownMenu } from '@/components/tiptap-ui/list-dropdown-menu'
import { MarkButton } from '@/components/tiptap-ui/mark-button'
import { UndoRedoButton } from '@/components/tiptap-ui/undo-redo-button'
import { ButtonGroup } from '@/components/tiptap-ui-primitive/button-group'
import { Separator } from '@/components/tiptap-ui-primitive/separator'

const MAX_PASTE_IMAGE_SIZE = 10 * 1024 * 1024

const RichTextImage = Node.create({
  name: 'image',
  group: 'block',
  inline: false,
  atom: true,
  draggable: true,

  addAttributes() {
    return {
      src: { default: null },
      alt: { default: null },
      title: { default: null },
    }
  },

  parseHTML() {
    return [{ tag: 'img[src]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['img', mergeAttributes(HTMLAttributes)]
  },
})

const turndown = new TurndownService({ headingStyle: 'atx' })
turndown.addRule('opendeskPreserveMarkHighlight', {
  filter: 'mark',
  replacement(content, node) {
    const el = node as HTMLElement
    const dataColor = el.getAttribute('data-color')
    const style = el.getAttribute('style')
    const parts = [
      dataColor ? `data-color="${dataColor}"` : '',
      style ? `style="${style.replace(/"/g, '&quot;')}"` : '',
    ].filter(Boolean)
    const attr = parts.length > 0 ? ` ${parts.join(' ')}` : ''
    return `<mark${attr}>${content}</mark>`
  },
})

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
  const uploadMutation = useUploadCustomFieldFile()
  const [pasteImageError, setPasteImageError] = useState<string | null>(null)
  const [isPastingImage, setIsPastingImage] = useState(false)
  const editorRef = useRef<Editor | null>(null)

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
        heading: { levels: [1, 2, 3, 4, 5, 6] },
        // Custom Link extension below; avoid registering Link twice.
        link: false,
      }),
      Placeholder.configure({
        placeholder: placeholder || '…',
      }),
      Link.configure({
        openOnClick: false,
        autolink: true,
        defaultProtocol: 'https',
      }),
      Highlight.configure({
        multicolor: true,
      }),
      RichTextImage,
    ],
    content: contentForEditor,
    editable: !disabled,
    editorProps: {
      attributes: {
        class: cn(
          'prose prose-sm dark:prose-invert max-w-none min-h-[140px] px-3 py-2 outline-none',
          'prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1',
          richTextListStyleClass,
        ),
      },
      handlePaste: (_view, event) => {
        if (disabled) return false

        const clipboard = event.clipboardData
        const files = Array.from(clipboard?.items ?? [])
          .filter((item) => item.kind === 'file')
          .map((item) => item.getAsFile())
          .filter((file): file is File => !!file && file.type.startsWith('image/'))

        if (files.length === 0) return false

        event.preventDefault()
        setPasteImageError(null)
        setIsPastingImage(true)

        void (async () => {
          try {
            for (const file of files) {
              if (file.size > MAX_PASTE_IMAGE_SIZE) {
                setPasteImageError(`图片过大: ${file.name || 'clipboard image'}`)
                continue
              }

              const meta = await uploadMutation.mutateAsync(file)
              editorRef.current
                ?.chain()
                .focus()
                .insertContent({
                  type: 'image',
                  attrs: {
                    src: meta.url,
                    alt: meta.name || file.name || 'pasted image',
                    title: meta.name || file.name || null,
                  },
                })
                .run()
            }
          } catch {
            setPasteImageError('图片上传失败')
          } finally {
            setIsPastingImage(false)
          }
        })()

        return true
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
    editorRef.current = editor
  }, [editor])

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
        <ButtonGroup>
          <HeadingDropdownMenu editor={editor} levels={[1, 2, 3, 4, 5, 6]} disabled={disabled} />
        </ButtonGroup>
        <Separator />
        <ButtonGroup>
          <MarkButton editor={editor} type="bold" disabled={disabled} />
          <MarkButton editor={editor} type="italic" disabled={disabled} />
          <MarkButton editor={editor} type="strike" disabled={disabled} />
          <ColorHighlightPopover editor={editor} disabled={disabled} />
        </ButtonGroup>
        <Separator />
        <ButtonGroup>
          <ListDropdownMenu editor={editor} types={['bulletList', 'orderedList']} disabled={disabled} />
          <BlockquoteButton editor={editor} disabled={disabled} />
        </ButtonGroup>
        <Separator />
        <ButtonGroup>
          <LinkPopover editor={editor} disabled={disabled} autoOpenOnLinkActive={false} />
        </ButtonGroup>
        <Separator />
        <ButtonGroup>
          <UndoRedoButton editor={editor} action="undo" disabled={disabled} />
          <UndoRedoButton editor={editor} action="redo" disabled={disabled} />
        </ButtonGroup>
      </div>
      {(isPastingImage || pasteImageError) && (
        <div className="border-b border-border px-3 py-1 text-xs">
          {isPastingImage ? (
            <span className="text-muted-foreground">图片上传中…</span>
          ) : (
            <span className="text-destructive">{pasteImageError}</span>
          )}
        </div>
      )}
      <EditorContent editor={editor} className="max-h-[min(360px,50vh)] overflow-y-auto" />
    </div>
  )
}

