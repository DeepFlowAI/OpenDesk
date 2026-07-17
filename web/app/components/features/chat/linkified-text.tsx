'use client'

const HTTP_URL_PATTERN = /https?:\/\/[^\s<>"'`]+/gi
const TRAILING_URL_PUNCTUATION_PATTERN = /[.,!?;:)\]}，。！？；：、）】》]+$/

type TextLinkSegment = {
  type: 'link'
  text: string
  href: string
} | {
  type: 'text'
  text: string
}

function splitHttpLinks(content: string): TextLinkSegment[] {
  const segments: TextLinkSegment[] = []
  let lastIndex = 0

  for (const match of content.matchAll(HTTP_URL_PATTERN)) {
    const matchedText = match[0]
    const matchIndex = match.index ?? 0
    const linkText = matchedText.replace(TRAILING_URL_PUNCTUATION_PATTERN, '')
    const trailingText = matchedText.slice(linkText.length)

    if (matchIndex > lastIndex) {
      segments.push({ type: 'text', text: content.slice(lastIndex, matchIndex) })
    }

    segments.push({ type: 'link', text: linkText, href: linkText })
    if (trailingText) segments.push({ type: 'text', text: trailingText })
    lastIndex = matchIndex + matchedText.length
  }

  if (lastIndex < content.length) {
    segments.push({ type: 'text', text: content.slice(lastIndex) })
  }

  return segments.length > 0 ? segments : [{ type: 'text', text: content }]
}

export function LinkifiedText({ content }: { content: string }) {
  return (
    <>
      {splitHttpLinks(content).map((segment, index) => (
        segment.type === 'link' ? (
          <a
            key={`${segment.href}-${index}`}
            href={segment.href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-current underline underline-offset-2 hover:opacity-80"
          >
            {segment.text}
          </a>
        ) : (
          <span key={`text-${index}`}>{segment.text}</span>
        )
      ))}
    </>
  )
}
