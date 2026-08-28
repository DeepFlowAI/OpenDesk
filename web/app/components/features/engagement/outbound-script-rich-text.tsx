'use client'

import { useEffect } from 'react'
import Link from '@tiptap/extension-link'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { IconBold, IconLink, IconList, IconListNumbers } from '@tabler/icons-react'

import { cn } from '@/lib/utils'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'

export function OutboundScriptRichText({
  value,
  onChange,
  placeholder,
  className,
}: {
  value?: string | null
  onChange: (value: string | null) => void
  placeholder: string
  className?: string
}) {
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        blockquote: false,
        code: false,
        codeBlock: false,
        heading: false,
        horizontalRule: false,
        italic: false,
        link: false,
        strike: false,
      }),
      Link.configure({ openOnClick: false, autolink: true, defaultProtocol: 'https' }),
    ],
    content: value || '<p></p>',
    editorProps: {
      attributes: { class: cn('min-h-24 px-3 py-2 text-sm outline-none', richTextListStyleClass) },
    },
    onUpdate: ({ editor: current }) => onChange(current.isEmpty ? null : current.getHTML()),
  })

  useEffect(() => {
    if (!editor || editor.isDestroyed) return
    const next = value || '<p></p>'
    if (editor.getHTML() !== next) editor.commands.setContent(next, { emitUpdate: false })
  }, [editor, value])

  if (!editor) return <div className="h-28 animate-pulse rounded-md bg-muted" />

  const setLink = () => {
    const previous = editor.getAttributes('link').href as string | undefined
    const href = window.prompt('链接地址', previous ?? 'https://')
    if (href === null) return
    if (!href.trim()) editor.chain().focus().unsetLink().run()
    else editor.chain().focus().extendMarkRange('link').setLink({ href: href.trim() }).run()
  }

  return (
    <div className={cn('overflow-hidden rounded-md border border-border bg-background', className)}>
      <div className="flex items-center gap-1 border-b border-border px-2 py-1.5">
        <ToolbarButton label="加粗" active={editor.isActive('bold')} onClick={() => editor.chain().focus().toggleBold().run()}><IconBold size={15} /></ToolbarButton>
        <ToolbarButton label="无序列表" active={editor.isActive('bulletList')} onClick={() => editor.chain().focus().toggleBulletList().run()}><IconList size={15} /></ToolbarButton>
        <ToolbarButton label="有序列表" active={editor.isActive('orderedList')} onClick={() => editor.chain().focus().toggleOrderedList().run()}><IconListNumbers size={15} /></ToolbarButton>
        <ToolbarButton label="链接" active={editor.isActive('link')} onClick={setLink}><IconLink size={15} /></ToolbarButton>
      </div>
      <EditorContent editor={editor} aria-label={placeholder} />
    </div>
  )
}

function ToolbarButton({ label, active, onClick, children }: { label: string; active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" title={label} aria-label={label} onClick={onClick} className={cn('rounded p-1.5 text-muted-foreground hover:bg-muted', active && 'bg-muted text-foreground')}>
      {children}
    </button>
  )
}
