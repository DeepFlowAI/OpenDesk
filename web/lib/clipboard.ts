// Clipboard helpers for copying message text and images.

export async function copyPlainTextToClipboard(text: string): Promise<boolean> {
  try {
    if (!navigator.clipboard?.writeText) return false
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export function htmlToPlainText(html: string): string {
  if (typeof document === 'undefined') return html
  const doc = new DOMParser().parseFromString(html, 'text/html')
  return (doc.body.textContent ?? '').trim()
}

// Returns the highlighted text only when the current selection intersects the
// given node, so right-clicking a message copies just what the user selected.
export function getSelectionTextWithin(node: Node): string {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed) return ''
  const text = selection.toString()
  if (!text.trim()) return ''
  const anchorInside = selection.anchorNode ? node.contains(selection.anchorNode) : false
  const focusInside = selection.focusNode ? node.contains(selection.focusNode) : false
  return anchorInside || focusInside ? text : ''
}

async function convertBlobToPng(blob: Blob): Promise<Blob> {
  const bitmap = await createImageBitmap(blob)
  const canvas = document.createElement('canvas')
  canvas.width = bitmap.width
  canvas.height = bitmap.height
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    bitmap.close()
    throw new Error('Canvas 2D context unavailable')
  }
  ctx.drawImage(bitmap, 0, 0)
  bitmap.close()
  return await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((result) => {
      if (result) resolve(result)
      else reject(new Error('Failed to encode image as PNG'))
    }, 'image/png')
  })
}

// Fetches an image and writes it to the clipboard. The Clipboard API only
// guarantees image/png support, so non-PNG images are re-encoded via canvas.
export async function copyImageUrlToClipboard(url: string): Promise<boolean> {
  try {
    if (typeof ClipboardItem === 'undefined' || !navigator.clipboard?.write) return false
    const response = await fetch(url)
    if (!response.ok) return false
    const blob = await response.blob()
    const pngBlob = blob.type === 'image/png' ? blob : await convertBlobToPng(blob)
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': pngBlob })])
    return true
  } catch {
    return false
  }
}

