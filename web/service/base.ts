import ky from 'ky'

// API base URL must be supplied via NEXT_PUBLIC_API_URL (see web/.env.example).
// We intentionally avoid a hard-coded localhost fallback so production builds
// never silently target an internal/dev address.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ''

const client = ky.create({
  prefixUrl: API_BASE,
  timeout: 30000,
  hooks: {
    beforeRequest: [
      (request) => {
        const token = localStorage.getItem('auth_token')
        if (token) request.headers.set('Authorization', `Bearer ${token}`)
      },
    ],
    afterResponse: [
      async (_request, _options, response) => {
        if (response.status === 401) {
          localStorage.removeItem('auth_token')
          window.location.href = '/login'
        }
      },
    ],
  },
})

export const get = <T>(url: string, options?: Parameters<typeof client.get>[1]) =>
  client.get(url, options).json<T>()

export const getBlob = async (url: string, options?: Parameters<typeof client.get>[1]) => {
  const response = await client.get(url, options)
  return { blob: await response.blob(), headers: response.headers }
}

export const post = <T>(url: string, options?: Parameters<typeof client.post>[1]) =>
  client.post(url, options).json<T>()

/** Multipart upload — uses same base URL and auth hooks as other API calls */
export const postForm = <T>(url: string, formData: FormData, timeoutMs = 60000) =>
  client.post(url, { body: formData, timeout: timeoutMs }).json<T>()

export const put = <T>(url: string, options?: Parameters<typeof client.put>[1]) =>
  client.put(url, options).json<T>()

export const patch = <T>(url: string, options?: Parameters<typeof client.patch>[1]) =>
  client.patch(url, options).json<T>()

export const del = <T = void>(url: string, options?: Parameters<typeof client.delete>[1]) =>
  client.delete(url, options).json<T>()
