const WORKSPACE_NOTIFICATION_ALERT_SRC = '/audio/notification-alert.mp3'
const AUDIO_UNLOCK_EVENTS = ['pointerdown', 'keydown', 'touchstart'] as const

let alertAudio: HTMLAudioElement | null = null
let alertAudioUnlocked = false

function getAlertAudio(): HTMLAudioElement | null {
  if (typeof window === 'undefined') return null
  if (!alertAudio) {
    alertAudio = new Audio(WORKSPACE_NOTIFICATION_ALERT_SRC)
    alertAudio.preload = 'auto'
  }
  return alertAudio
}

function playAlertAudio(): void {
  const audio = getAlertAudio()
  if (!audio) return

  audio.pause()
  audio.currentTime = 0
  audio.muted = false
  audio.play().catch(() => {
    // Browsers may block autoplay until the user interacts with the page.
  })
}

function unlockAlertAudio(): void {
  if (alertAudioUnlocked) return

  const audio = getAlertAudio()
  if (!audio) return

  audio.muted = true
  audio.currentTime = 0
  audio
    .play()
    .then(() => {
      audio.pause()
      audio.currentTime = 0
      audio.muted = false
      alertAudioUnlocked = true
    })
    .catch(() => {
      audio.muted = false
    })
}

/** Bind gesture listeners so background Socket.IO alerts can play after refresh. */
export function bindWorkspaceNotificationAlertUnlock(): () => void {
  AUDIO_UNLOCK_EVENTS.forEach((eventName) => {
    document.addEventListener(eventName, unlockAlertAudio, { capture: true })
  })

  return () => {
    AUDIO_UNLOCK_EVENTS.forEach((eventName) => {
      document.removeEventListener(eventName, unlockAlertAudio, { capture: true })
    })
  }
}

/** Visitor message alert — only when the tab is in the background. */
export function playWorkspaceMessageAlert(): void {
  if (document.visibilityState === 'visible') return
  playAlertAudio()
}

/** Session assignment alert — new conversation, transfer, queue/offline assign. */
export function playWorkspaceSessionAlert(): void {
  playAlertAudio()
}
