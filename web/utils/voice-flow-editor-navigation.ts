type RouterLike = {
  push: (url: string) => void
  replace?: (url: string) => void
}

/** Close the editor tab when opened from the list, otherwise navigate back to the list page. */
export function leaveVoiceFlowEditor(router: RouterLike, mode: 'push' | 'replace' = 'push') {
  if (typeof window !== 'undefined' && window.opener) {
    window.close()
    return
  }
  const navigate = mode === 'replace' && router.replace ? router.replace : router.push
  navigate('/flow-studio/voice-flows')
}
