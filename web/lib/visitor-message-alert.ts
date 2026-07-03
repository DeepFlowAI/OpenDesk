const VISITOR_MESSAGE_ALERT_SRC = '/audio/notification-alert.mp3'
const VISITOR_MESSAGE_ALERT_STORAGE_KEY = 'opendesk:visitor-message-alert-enabled'
const AUDIO_UNLOCK_EVENTS = ['pointerdown', 'keydown', 'touchstart'] as const

let alertAudio: HTMLAudioElement | null = null
let alertAudioUnlocked = false

function getAlertAudio(): HTMLAudioElement | null {
  if (typeof window === 'undefined') return null
  if (!alertAudio) {
    alertAudio = new Audio(VISITOR_MESSAGE_ALERT_SRC)
    alertAudio.preload = 'auto'
  }
  return alertAudio
}

export function readVisitorMessageAlertEnabled(): boolean {
  if (typeof window === 'undefined') return true
  try {
    return window.localStorage.getItem(VISITOR_MESSAGE_ALERT_STORAGE_KEY) !== '0'
  } catch {
    return true
  }
}

export function setVisitorMessageAlertEnabled(enabled: boolean): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(VISITOR_MESSAGE_ALERT_STORAGE_KEY, enabled ? '1' : '0')
  } catch {
    // A disabled or full localStorage should not break the visitor chat.
  }
}

export function stopVisitorMessageAlert(): void {
  const audio = getAlertAudio()
  if (!audio) return
  audio.pause()
  audio.currentTime = 0
}

export function playVisitorMessageAlert(): void {
  const audio = getAlertAudio()
  if (!audio) return

  audio.pause()
  audio.currentTime = 0
  audio.muted = false
  audio.play().catch(() => {
    // Browsers may block autoplay until the user interacts with the page.
  })
}

export function unlockVisitorMessageAlert(): void {
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

export function bindVisitorMessageAlertUnlock(): () => void {
  if (typeof document === 'undefined') return () => {}

  AUDIO_UNLOCK_EVENTS.forEach((eventName) => {
    document.addEventListener(eventName, unlockVisitorMessageAlert, { capture: true })
  })

  return () => {
    AUDIO_UNLOCK_EVENTS.forEach((eventName) => {
      document.removeEventListener(eventName, unlockVisitorMessageAlert, { capture: true })
    })
  }
}
