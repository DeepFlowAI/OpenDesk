import { copyFile, mkdir } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const source = require.resolve('@embedpdf/pdfium/pdfium.wasm')
const target = resolve(webRoot, 'public/vendor/embedpdf/pdfium.wasm')

await mkdir(dirname(target), { recursive: true })
await copyFile(source, target)
