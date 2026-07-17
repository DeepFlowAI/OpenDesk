import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'

// Vitest setup for the web app.
// - The explicit `@` alias also covers imports made directly by test files,
//   which the app tsconfig intentionally excludes. `tsconfigPaths` still
//   resolves any additional path mappings used by application source files.
// - JSX uses the automatic runtime, matching Next.js, so importing `.tsx`
//   modules (even just to exercise their pure functions) works without a
//   manual `import React`. tsconfig sets `jsx: preserve` for Next, so it must
//   be overridden here or the bundler cannot parse the JSX.
// - `jsdom` provides a browser-like environment; harmless for pure-function
//   tests and ready for component tests later.
export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('.', import.meta.url)),
    },
    tsconfigPaths: true,
  },
  oxc: {
    jsx: {
      runtime: 'automatic',
      importSource: 'react',
    },
  },
  test: {
    environment: 'jsdom',
    include: ['**/*.test.{ts,tsx}'],
    exclude: ['node_modules', '.next', 'dist'],
  },
})
