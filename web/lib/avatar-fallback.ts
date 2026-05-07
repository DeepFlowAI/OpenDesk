/**
 * Deterministic fallback styling when no avatar image URL is available.
 */

const HUES = [210, 160, 280, 32, 340, 190, 24, 262, 130, 310]

/**
 * One visible character for the avatar: first CJK char or first Latin letter.
 */
export function singleAvatarLetter(name: string): string {
  const t = name.trim()
  if (!t) return '?'
  const ch = t[0]!
  if (/[\u4e00-\u9fff]/.test(ch)) return ch
  if (/[a-zA-Z]/.test(ch)) return ch.toUpperCase()
  return ch
}

/** Stable saturated background for a display name (readable with white text). */
export function avatarBackgroundForName(name: string): string {
  const t = name.trim() || '?'
  let h = 0
  for (let i = 0; i < t.length; i += 1) h = (h * 33 + t.charCodeAt(i)) >>> 0
  const hue = HUES[h % HUES.length]!
  return `hsl(${hue} 48% 44%)`
}
