const fs = require('fs')
const path = require('path')

const appEnv = process.env.APP_ENV || 'dev'

/**
 * @param {string} envPath
 * @param {{ onlyIfUnset?: boolean }} [opts]
 */
function loadDotenvFile(envPath, opts = {}) {
  const { onlyIfUnset = false } = opts
  if (!fs.existsSync(envPath)) return
  const lines = fs.readFileSync(envPath, 'utf-8').split('\n')
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const [key, ...rest] = trimmed.split('=')
    if (!key) continue
    if (onlyIfUnset && process.env[key]) continue
    process.env[key] = rest.join('=')
  }
}

const repoRoot = path.resolve(__dirname, '..')
const webLocalEnv = path.resolve(__dirname, `.env.${appEnv}`)
const webPrivateEnv = path.join(repoRoot, 'private', 'env', `web.env.${appEnv}`)
// Local .env first; private/env overrides (same precedence as server settings).
loadDotenvFile(webLocalEnv, { onlyIfUnset: true })
loadDotenvFile(webPrivateEnv, { onlyIfUnset: false })

// Some browser-shipped libraries (e.g. jit-viewer, socket.io-client's debug
// build) statically reference Node built-ins (`fs`, `util`, `tty`, ...) inside
// unreachable code paths. The bundler still needs to resolve those specifiers
// for the client target. Alias them to an empty stub *only* on `browser`, so
// SSR / RSC keeps using real Node modules.
const emptyStub = './stubs/empty.js'
const browserStub = { browser: emptyStub }

/** @type {import('next').NextConfig} */
const nextConfig = {
  turbopack: {
    resolveAlias: {
      fs: browserStub,
      util: browserStub,
      tty: browserStub,
      child_process: browserStub,
      url: browserStub,
    },
  },
  webpack: (config, { isServer }) => {
    if (!isServer) {
      config.resolve = config.resolve || {}
      config.resolve.fallback = {
        ...(config.resolve.fallback || {}),
        fs: false,
        util: false,
        tty: false,
        child_process: false,
        url: false,
      }
    }
    return config
  },
}

module.exports = nextConfig
