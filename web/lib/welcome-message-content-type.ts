export function isHumanWelcomeContentType(contentType: string): boolean {
  return contentType === 'welcome'
}

export function isBotWelcomeContentType(contentType: string): boolean {
  return contentType === 'bot_welcome'
}

export function isWelcomeLikeContentType(contentType: string): boolean {
  return isHumanWelcomeContentType(contentType) || isBotWelcomeContentType(contentType)
}
