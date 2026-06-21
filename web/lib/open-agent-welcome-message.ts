import type { OpenAgentFAQ, OpenAgentWelcomeMessageBlock } from '@/models/channel'

export function markdownHasVisibleContent(content: string) {
  const imageMatch = /!\[[^\]]*]\((https?:\/\/|\/)[^)]+?\)/i.test(content)
  const text = content
    .replace(/!\[[^\]]*]\([^)]+\)/g, '')
    .replace(/\[[^\]]+]\([^)]+\)/g, '$1')
    .replace(/[`*_>#\-\+\=\[\]\(\).!|~]/g, '')
    .trim()
  return imageMatch || text.length > 0
}

export function isValidOpenAgentWelcomeBlock(block: OpenAgentWelcomeMessageBlock) {
  if (block.type === 'markdown') return markdownHasVisibleContent(block.content)
  return block.embed_code.trim().length > 0 && block.height > 0
}

export function getOpenAgentWelcomeBlocksFromMetadata(
  metadata?: Record<string, unknown>,
): OpenAgentWelcomeMessageBlock[] {
  const value = metadata?.open_agent_welcome_blocks
  if (!Array.isArray(value)) return []

  return value.flatMap((item): OpenAgentWelcomeMessageBlock[] => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return []
    const record = item as Record<string, unknown>

    if (record.type === 'markdown') {
      const content = typeof record.content === 'string' ? record.content : ''
      const block: OpenAgentWelcomeMessageBlock = { type: 'markdown', content }
      return isValidOpenAgentWelcomeBlock(block) ? [block] : []
    }

    if (record.type === 'embed') {
      const embedCode = typeof record.embed_code === 'string' ? record.embed_code : ''
      const height = typeof record.height === 'number' && Number.isFinite(record.height)
        ? record.height
        : 360
      const block: OpenAgentWelcomeMessageBlock = {
        type: 'embed',
        embed_code: embedCode,
        height,
      }
      return isValidOpenAgentWelcomeBlock(block) ? [block] : []
    }

    return []
  })
}

export function getValidOpenAgentFAQ(faq?: OpenAgentFAQ | null): OpenAgentFAQ | null {
  if (!faq?.enabled) return null

  const categories = faq.categories.flatMap((category) => {
    const name = category.name.trim()
    if (!name) return []

    const questions = category.questions.flatMap((question) => {
      const text = question.text.trim()
      return text ? [{ text }] : []
    })
    return questions.length > 0 ? [{ name, questions }] : []
  })

  if (categories.length === 0) return null
  const title = faq.title.trim() || '常见问题'
  return { enabled: true, title, categories }
}

const OPEN_AGENT_WELCOME_EMBED_BASE_STYLE = `<style>
  html, body {
    margin: 0;
    width: 100%;
    height: 100%;
    min-height: 100%;
    background: transparent;
    overflow: hidden;
  }
  *, *::before, *::after { box-sizing: border-box; }
  iframe, video, img, object, embed { max-width: 100%; }
</style>`

function isCompleteHtmlDocument(embedCode: string) {
  return /(?:<!doctype\s+html|<html[\s>])/i.test(embedCode)
}

function injectOpenAgentWelcomeEmbedBaseStyle(html: string) {
  if (/<\/head>/i.test(html)) {
    return html.replace(/<\/head>/i, `${OPEN_AGENT_WELCOME_EMBED_BASE_STYLE}</head>`)
  }

  if (/<html[\s>]/i.test(html)) {
    return html.replace(/<html([^>]*)>/i, `<html$1><head>${OPEN_AGENT_WELCOME_EMBED_BASE_STYLE}</head>`)
  }

  return `${OPEN_AGENT_WELCOME_EMBED_BASE_STYLE}${html}`
}

export function buildOpenAgentWelcomeEmbedSrcDoc(embedCode: string) {
  if (isCompleteHtmlDocument(embedCode)) {
    return injectOpenAgentWelcomeEmbedBaseStyle(embedCode)
  }

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta http-equiv="x-ua-compatible" content="IE=edge" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  ${OPEN_AGENT_WELCOME_EMBED_BASE_STYLE}
</head>
<body>${embedCode}</body>
</html>`
}
