type FloatingMenuSize = {
  width: number
  height: number
}

type FloatingMenuPosition = {
  x: number
  y: number
}

const DEFAULT_VIEWPORT_MARGIN = 8

export function getBoundedFixedMenuPosition(
  position: FloatingMenuPosition,
  size: FloatingMenuSize,
  margin = DEFAULT_VIEWPORT_MARGIN,
): FloatingMenuPosition {
  if (typeof window === 'undefined') return position

  const viewport = window.visualViewport
  const viewportLeft = viewport?.offsetLeft ?? 0
  const viewportTop = viewport?.offsetTop ?? 0
  const viewportWidth = viewport?.width ?? window.innerWidth
  const viewportHeight = viewport?.height ?? window.innerHeight

  const minX = viewportLeft + margin
  const minY = viewportTop + margin
  const maxX = viewportLeft + viewportWidth - size.width - margin
  const maxY = viewportTop + viewportHeight - size.height - margin

  return {
    x: Math.max(minX, Math.min(position.x, maxX)),
    y: Math.max(minY, Math.min(position.y, maxY)),
  }
}
