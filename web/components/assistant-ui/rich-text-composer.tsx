'use client'

import { useCallback, useEffect, useRef, useState, type ChangeEvent, type KeyboardEvent, type ReactNode } from 'react'
import { EditorContent, useEditor, type Editor } from '@tiptap/react'
import { Mark, Node, mergeAttributes } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Link from '@tiptap/extension-link'
import {
  IconBold,
  IconH1,
  IconItalic,
  IconLink,
  IconList,
  IconListNumbers,
  IconPalette,
  IconPhotoPlus,
  IconQuote,
  IconTypography,
} from '@tabler/icons-react'
import { EmojiPicker } from './emoji-picker'
import { cn } from '@/lib/utils'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { prepareRichTextMessageHtml } from '@/lib/rich-text-message'
import type { ConversationFileUploadResponse } from '@/models/conversation-file'
import type { EmojiTargetConfig } from '@/models/emoji-setting'

/** Fixed height for the inline formatting toolbar below the editor (matches h-9). */
export const RICH_TEXT_COMPOSER_TOOLBAR_HEIGHT = 36

const RICH_TEXT_EDITOR_DEFAULT_HEIGHT = 22
const RICH_TEXT_EDITOR_MAX_HEIGHT = 168

type RichTextComposerProps = {
  value: string
  disabled?: boolean
  uploading?: boolean
  locale: 'zh' | 'en'
  editorHeight?: number
  editorMaxHeight?: number
  endSafeArea?: boolean
  autoFocusKey?: number | string | null
  onChange: (html: string) => void
  onImageUpload: (file: File) => Promise<ConversationFileUploadResponse>
  onAttachmentPaste?: (file: File) => void
  onUploadingChange?: (uploading: boolean) => void
  emojiConfig?: EmojiTargetConfig | null
}

type HtmlImageSource = {
  src: string
  name?: string | null
}

type TextColorOption = {
  color: string
  previewClass: string
  zh: string
  en: string
}

const TEXT_COLOR_OPTIONS: TextColorOption[] = [
  { color: '#1a1a1a', previewClass: 'bg-[#1a1a1a]', zh: '黑色', en: 'Black' },
  { color: '#737373', previewClass: 'bg-[#737373]', zh: '灰色', en: 'Gray' },
  { color: '#dc2626', previewClass: 'bg-[#dc2626]', zh: '红色', en: 'Red' },
  { color: '#f97316', previewClass: 'bg-[#f97316]', zh: '橙色', en: 'Orange' },
  { color: '#16a34a', previewClass: 'bg-[#16a34a]', zh: '绿色', en: 'Green' },
  { color: '#2563eb', previewClass: 'bg-[#2563eb]', zh: '蓝色', en: 'Blue' },
  { color: '#7c3aed', previewClass: 'bg-[#7c3aed]', zh: '紫色', en: 'Purple' },
  { color: '#db2777', previewClass: 'bg-[#db2777]', zh: '粉色', en: 'Pink' },
]

const TextColor = Mark.create({
  name: 'textColor',

  addAttributes() {
    return {
      color: {
        default: null,
        parseHTML: (element) => element.style.color || null,
        renderHTML: (attributes) => {
          if (!attributes.color) return {}
          return { style: `color: ${attributes.color}` }
        },
      },
    }
  },

  parseHTML() {
    return [{ tag: 'span[style*=color]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['span', mergeAttributes(HTMLAttributes), 0]
  },
})

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
      fileId: {
        default: null,
        parseHTML: (element) => element.getAttribute('data-file-id'),
        renderHTML: (attributes) => attributes.fileId ? { 'data-file-id': attributes.fileId } : {},
      },
      name: {
        default: null,
        parseHTML: (element) => element.getAttribute('data-name'),
        renderHTML: (attributes) => attributes.name ? { 'data-name': attributes.name } : {},
      },
    }
  },

  parseHTML() {
    return [{ tag: 'img' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['img', mergeAttributes(HTMLAttributes)]
  },
})

function ToolbarButton({
  active,
  disabled,
  label,
  onClick,
  children,
}: {
  active?: boolean
  disabled?: boolean
  label: string
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      className={cn(
        'flex h-7 w-7 items-center justify-center rounded-md text-[#737373] transition-colors hover:bg-neutral-100 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40',
        active && 'bg-neutral-100 text-foreground',
      )}
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

function TextColorPicker({
  editor,
  disabled,
  locale,
}: {
  editor: Editor
  disabled?: boolean
  locale: 'zh' | 'en'
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const selectedColor = typeof editor.getAttributes('textColor').color === 'string'
    ? String(editor.getAttributes('textColor').color).toLowerCase()
    : null
  const selectedOption = TEXT_COLOR_OPTIONS.find((item) => item.color === selectedColor)
  const label = locale === 'zh' ? '文字颜色' : 'Text color'
  const clearLabel = locale === 'zh' ? '默认颜色' : 'Default color'

  useEffect(() => {
    if (!open) return

    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as globalThis.Node)) {
        setOpen(false)
      }
    }
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  useEffect(() => {
    if (disabled) setOpen(false)
  }, [disabled])

  const applyColor = (color: string) => {
    editor.chain().focus().setMark('textColor', { color }).run()
    setOpen(false)
  }

  const clearColor = () => {
    editor.chain().focus().unsetMark('textColor').run()
    setOpen(false)
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        className={cn(
          'relative flex h-7 w-7 items-center justify-center rounded-md text-[#737373] transition-colors hover:bg-neutral-100 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40',
          open && 'bg-neutral-100 text-foreground',
        )}
        aria-label={label}
        title={label}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
      >
        <IconPalette size={15} stroke={1.8} />
        <span
          className={cn(
            'absolute bottom-1 h-0.5 w-3 rounded-full',
            selectedOption?.previewClass ?? 'bg-[#1a1a1a]',
          )}
        />
      </button>
      {open && (
        <div className="absolute bottom-8 left-0 z-40 w-36 rounded-lg border border-border bg-white p-2 shadow-lg">
          <button
            type="button"
            className="mb-1 flex h-7 w-full items-center rounded-md px-2 text-left text-xs text-foreground transition-colors hover:bg-muted"
            onMouseDown={(event) => event.preventDefault()}
            onClick={clearColor}
          >
            {clearLabel}
          </button>
          <div className="grid grid-cols-4 gap-1">
            {TEXT_COLOR_OPTIONS.map((item) => {
              const active = item.color === selectedColor
              const name = locale === 'zh' ? item.zh : item.en
              return (
                <button
                  key={item.color}
                  type="button"
                  className={cn(
                    'flex h-7 w-7 items-center justify-center rounded-md border border-transparent transition-colors hover:bg-muted',
                    active && 'border-foreground bg-muted',
                  )}
                  aria-label={`${label}: ${name}`}
                  title={name}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => applyColor(item.color)}
                >
                  <span className={cn('h-4 w-4 rounded-full border border-black/10', item.previewClass)} />
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function insertImage(editor: Editor | null, uploaded: ConversationFileUploadResponse) {
  if (!editor) return
  editor
    .chain()
    .focus()
    .insertContent({
      type: 'image',
      attrs: {
        src: uploaded.access_url,
        fileId: uploaded.file_id,
        name: uploaded.name,
        alt: uploaded.name,
        title: uploaded.name,
      },
    })
    .run()
}

function getClipboardHtmlImageSources(data: DataTransfer): HtmlImageSource[] {
  const html = data.getData('text/html')
  if (!html || typeof DOMParser === 'undefined') return []

  const doc = new DOMParser().parseFromString(html, 'text/html')
  return Array.from(doc.querySelectorAll<HTMLImageElement>('img[src]'))
    .map((img) => ({
      src: img.getAttribute('src')?.trim() ?? '',
      name: img.getAttribute('alt') || img.getAttribute('title'),
    }))
    .filter((item) => item.src.length > 0)
}

function imageFileNameFromSource(source: HtmlImageSource, type: string): string {
  const fallbackExt = type.split('/')[1]?.split(';')[0] || 'png'
  const rawName = source.name?.trim()
  if (rawName) return rawName

  try {
    const url = new URL(source.src, window.location.href)
    const fromPath = url.pathname.split('/').filter(Boolean).pop()
    if (fromPath) return decodeURIComponent(fromPath)
  } catch {
    // Fall through to the generated filename.
  }

  return `pasted-image.${fallbackExt}`
}

async function imageSourceToFile(source: HtmlImageSource): Promise<File> {
  const response = await fetch(source.src)
  if (!response.ok) throw new Error('Image fetch failed')

  const blob = await response.blob()
  if (!blob.type.startsWith('image/')) throw new Error('Pasted image source is not an image')

  return new File([blob], imageFileNameFromSource(source, blob.type), {
    type: blob.type,
    lastModified: Date.now(),
  })
}

function getClipboardAttachmentFile(data: DataTransfer): File | null {
  for (const item of Array.from(data.items)) {
    if (item.kind !== 'file') continue
    const file = item.getAsFile()
    if (file && !file.type.startsWith('image/')) return file
  }

  for (const file of Array.from(data.files)) {
    if (!file.type.startsWith('image/')) return file
  }

  return null
}

function clampEditorHeight(height: number, maxHeight: number): number {
  return Math.min(maxHeight, Math.max(RICH_TEXT_EDITOR_DEFAULT_HEIGHT, height))
}

export function RichTextComposer({
  value,
  disabled = false,
  uploading = false,
  locale,
  editorHeight: editorHeightProp,
  editorMaxHeight = RICH_TEXT_EDITOR_MAX_HEIGHT,
  endSafeArea = false,
  autoFocusKey = null,
  onChange,
  onImageUpload,
  onAttachmentPaste,
  onUploadingChange,
  emojiConfig,
}: RichTextComposerProps) {
  const editorHeight = clampEditorHeight(editorHeightProp ?? RICH_TEXT_EDITOR_DEFAULT_HEIGHT, editorMaxHeight)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const editorRef = useRef<Editor | null>(null)
  const lastAutoFocusKeyRef = useRef<number | string | null>(null)
  const [imageError, setImageError] = useState<string | null>(null)
  const [showBlockMenu, setShowBlockMenu] = useState(false)
  const placeholder = locale === 'zh'
    ? '输入消息，输入 / 添加内容'
    : 'Type a message, use / to add blocks'
  const labels = {
    bold: locale === 'zh' ? '加粗' : 'Bold',
    italic: locale === 'zh' ? '斜体' : 'Italic',
    link: locale === 'zh' ? '链接' : 'Link',
    paragraph: locale === 'zh' ? '正文' : 'Paragraph',
    heading: locale === 'zh' ? '标题' : 'Heading',
    bulletList: locale === 'zh' ? '无序列表' : 'Bullet list',
    orderedList: locale === 'zh' ? '有序列表' : 'Ordered list',
    quote: locale === 'zh' ? '引用' : 'Quote',
    image: locale === 'zh' ? '图片' : 'Image',
    uploading: locale === 'zh' ? '图片上传中…' : 'Uploading image…',
    failed: locale === 'zh' ? '图片上传失败，请重试' : 'Image upload failed. Try again.',
  }

  const uploadImages = useCallback(
    async (files: File[]) => {
      if (files.length === 0 || disabled) return
      setImageError(null)
      onUploadingChange?.(true)
      try {
        for (const file of files) {
          const uploaded = await onImageUpload(file)
          insertImage(editorRef.current, uploaded)
        }
      } catch {
        setImageError(labels.failed)
      } finally {
        onUploadingChange?.(false)
      }
    },
    [disabled, labels.failed, onImageUpload, onUploadingChange],
  )

  const uploadHtmlImageSources = useCallback(
    async (sources: HtmlImageSource[]) => {
      if (sources.length === 0 || disabled) return
      setImageError(null)
      onUploadingChange?.(true)
      try {
        for (const source of sources) {
          const file = await imageSourceToFile(source)
          const uploaded = await onImageUpload(file)
          insertImage(editorRef.current, uploaded)
        }
      } catch {
        setImageError(labels.failed)
      } finally {
        onUploadingChange?.(false)
      }
    },
    [disabled, labels.failed, onImageUpload, onUploadingChange],
  )

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: { levels: [1] },
        link: false,
      }),
      Link.configure({
        openOnClick: false,
        autolink: true,
        defaultProtocol: 'https',
      }),
      TextColor,
      Placeholder.configure({ placeholder }),
      RichTextImage,
    ],
    content: value || '<p></p>',
    editable: !disabled,
    editorProps: {
      attributes: {
        class: cn(
          'px-0 py-0 text-sm leading-[22px] outline-none',
          'text-[#1a1a1a] [&_.is-editor-empty:first-child:before]:pointer-events-none',
          '[&_.is-editor-empty:first-child:before]:float-left [&_.is-editor-empty:first-child:before]:h-0',
          '[&_.is-editor-empty:first-child:before]:text-[#BBBBBB] [&_.is-editor-empty:first-child:before]:content-[attr(data-placeholder)]',
          richTextListStyleClass,
        ),
      },
      handlePaste: (_view, event) => {
        const images = Array.from(event.clipboardData?.items ?? [])
          .filter((item) => item.kind === 'file')
          .map((item) => item.getAsFile())
          .filter((file): file is File => Boolean(file && file.type.startsWith('image/')))

        if (images.length > 0) {
          event.preventDefault()
          void uploadImages(images)
          return true
        }

        const attachmentPasteHandler = onAttachmentPaste
        if (event.clipboardData && attachmentPasteHandler) {
          const attachment = getClipboardAttachmentFile(event.clipboardData)
          if (attachment) {
            event.preventDefault()
            attachmentPasteHandler(attachment)
            return true
          }
        }

        const htmlImages = event.clipboardData
          ? getClipboardHtmlImageSources(event.clipboardData)
          : []
        if (htmlImages.length === 0) return false

        event.preventDefault()
        void uploadHtmlImageSources(htmlImages)
        return true
      },
    },
    onUpdate: ({ editor: nextEditor }) => {
      const from = nextEditor.state.selection.from
      setShowBlockMenu(
        nextEditor.isActive('paragraph')
        && nextEditor.state.selection.empty
        && from > 1
        && nextEditor.state.doc.textBetween(from - 1, from) === '/',
      )
      onChange(nextEditor.getHTML())
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
    if (autoFocusKey == null || disabled || !editor || editor.isDestroyed) return
    if (lastAutoFocusKeyRef.current === autoFocusKey) return
    lastAutoFocusKeyRef.current = autoFocusKey
    window.requestAnimationFrame(() => {
      if (editor.isDestroyed || !editor.isEditable) return
      editor.commands.focus('end')
    })
  }, [autoFocusKey, disabled, editor])

  useEffect(() => {
    if (!editor || editor.isDestroyed || value === editor.getHTML()) return
    editor.commands.setContent(value || '<p></p>', { emitUpdate: false })
  }, [editor, value])

  const applyLink = useCallback(() => {
    if (!editor) return
    const previous = editor.getAttributes('link').href as string | undefined
    const href = window.prompt(labels.link, previous || 'https://')
    if (href === null) return
    if (!href.trim()) {
      editor.chain().focus().unsetLink().run()
      return
    }
    editor.chain().focus().extendMarkRange('link').setLink({ href: href.trim() }).run()
  }, [editor, labels.link])

  const handleImageInput = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.target.files ?? []).filter((file) => file.type.startsWith('image/'))
      event.target.value = ''
      void uploadImages(files)
    },
    [uploadImages],
  )

  const insertBlock = useCallback(
    (kind: 'paragraph' | 'heading' | 'bullet' | 'ordered' | 'quote' | 'image') => {
      if (!editor) return
      setShowBlockMenu(false)
      if (kind === 'paragraph') editor.chain().focus().setParagraph().run()
      if (kind === 'heading') editor.chain().focus().toggleHeading({ level: 1 }).run()
      if (kind === 'bullet') editor.chain().focus().toggleBulletList().run()
      if (kind === 'ordered') editor.chain().focus().toggleOrderedList().run()
      if (kind === 'quote') editor.chain().focus().toggleBlockquote().run()
      if (kind === 'image') fileInputRef.current?.click()
    },
    [editor],
  )

  const insertBlockFromMenu = useCallback(
    (kind: 'paragraph' | 'heading' | 'bullet' | 'ordered' | 'quote' | 'image') => {
      if (!editor) return
      const from = editor.state.selection.from
      if (from > 1 && editor.state.doc.textBetween(from - 1, from) === '/') {
        editor.chain().focus().deleteRange({ from: from - 1, to: from }).run()
      }
      insertBlock(kind)
    },
    [editor, insertBlock],
  )

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') editor?.commands.blur()
  }

  if (!editor) {
    return (
      <div
        className="animate-pulse rounded-md bg-muted/30"
        style={{ height: editorHeight + RICH_TEXT_COMPOSER_TOOLBAR_HEIGHT }}
      />
    )
  }

  return (
    <div className={cn('relative', endSafeArea && 'pr-9')} onKeyDown={handleKeyDown}>
      {(uploading || imageError) && (
        <div className="mb-2 rounded-md bg-muted px-2 py-1 text-xs">
          {uploading ? <span className="text-muted-foreground">{labels.uploading}</span> : <span className="text-destructive">{imageError}</span>}
        </div>
      )}
      <div
        className={cn('overflow-y-auto', endSafeArea && '[scrollbar-gutter:stable]')}
        style={{ height: editorHeight, maxHeight: editorMaxHeight }}
      >
        <EditorContent editor={editor} />
      </div>
      {showBlockMenu && (
        <div className="absolute left-0 top-8 z-20 grid w-48 gap-1 rounded-lg border border-border bg-white p-1 shadow-lg">
          {[
            { kind: 'paragraph' as const, label: labels.paragraph, icon: <IconTypography size={15} /> },
            { kind: 'heading' as const, label: labels.heading, icon: <IconH1 size={15} /> },
            { kind: 'bullet' as const, label: labels.bulletList, icon: <IconList size={15} /> },
            { kind: 'ordered' as const, label: labels.orderedList, icon: <IconListNumbers size={15} /> },
            { kind: 'quote' as const, label: labels.quote, icon: <IconQuote size={15} /> },
            { kind: 'image' as const, label: labels.image, icon: <IconPhotoPlus size={15} /> },
          ].map((item) => (
            <button
              key={item.kind}
              type="button"
              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-foreground hover:bg-muted"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => insertBlockFromMenu(item.kind)}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      )}
      <div
        className="flex shrink-0 items-center gap-0.5"
        style={{ height: RICH_TEXT_COMPOSER_TOOLBAR_HEIGHT }}
      >
        <ToolbarButton label={labels.bold} active={editor.isActive('bold')} disabled={disabled} onClick={() => editor.chain().focus().toggleBold().run()}>
          <IconBold size={15} stroke={1.8} />
        </ToolbarButton>
        <ToolbarButton label={labels.italic} active={editor.isActive('italic')} disabled={disabled} onClick={() => editor.chain().focus().toggleItalic().run()}>
          <IconItalic size={15} stroke={1.8} />
        </ToolbarButton>
        <ToolbarButton label={labels.link} active={editor.isActive('link')} disabled={disabled} onClick={applyLink}>
          <IconLink size={15} stroke={1.8} />
        </ToolbarButton>
        <TextColorPicker editor={editor} disabled={disabled} locale={locale} />
        <ToolbarButton label={labels.heading} active={editor.isActive('heading', { level: 1 })} disabled={disabled} onClick={() => insertBlock('heading')}>
          <IconH1 size={15} stroke={1.8} />
        </ToolbarButton>
        <ToolbarButton label={labels.bulletList} active={editor.isActive('bulletList')} disabled={disabled} onClick={() => insertBlock('bullet')}>
          <IconList size={15} stroke={1.8} />
        </ToolbarButton>
        <ToolbarButton label={labels.orderedList} active={editor.isActive('orderedList')} disabled={disabled} onClick={() => insertBlock('ordered')}>
          <IconListNumbers size={15} stroke={1.8} />
        </ToolbarButton>
        <ToolbarButton label={labels.quote} active={editor.isActive('blockquote')} disabled={disabled} onClick={() => insertBlock('quote')}>
          <IconQuote size={15} stroke={1.8} />
        </ToolbarButton>
        <ToolbarButton label={labels.image} disabled={disabled || uploading} onClick={() => insertBlock('image')}>
          <IconPhotoPlus size={15} stroke={1.8} />
        </ToolbarButton>
        <EmojiPicker
          config={emojiConfig}
          locale={locale}
          disabled={disabled}
          onEmojiPick={(emoji) => editor.chain().focus().insertContent(emoji).run()}
        />
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp"
        multiple
        className="hidden"
        onChange={handleImageInput}
      />
    </div>
  )
}

export function editorHtmlToSendableRichText(editor: Editor | null): string {
  return prepareRichTextMessageHtml(editor?.getHTML() ?? '')
}
