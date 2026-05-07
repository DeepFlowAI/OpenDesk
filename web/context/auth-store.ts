import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type User = {
  id: number
  username: string
  display_name: string | null
  avatar?: string | null
  roles: string[]
  tenant_id: number
}

type AuthState = {
  user: User | null
  token: string | null
  setAuth: (user: User, token: string) => void
  updateUser: (partial: Partial<Pick<User, 'display_name' | 'avatar'>>) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      setAuth: (user, token) => {
        set({ user, token })
        localStorage.setItem('auth_token', token)
      },
      updateUser: (partial) => {
        set((state) => ({
          user: state.user ? { ...state.user, ...partial } : null,
        }))
      },
      clearAuth: () => {
        set({ user: null, token: null })
        localStorage.removeItem('auth_token')
      },
    }),
    { name: 'app-auth' }
  )
)
