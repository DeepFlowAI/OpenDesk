'use client'

type SystemMessageProps = {
  content: string
}

export function SystemMessage({ content }: SystemMessageProps) {
  return (
    <div className="flex justify-center py-2">
      <span className="rounded-sm bg-muted px-3 py-1 text-xs text-muted-foreground">
        {content}
      </span>
    </div>
  )
}
