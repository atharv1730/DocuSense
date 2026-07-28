/**
 * API client for the backend.
 *
 * This file contains the API client for the backend.
 * It uses the NextAuth JWT token to authenticate requests to the backend.
 */
const API_URL = process.env.NEXT_PUBLIC_API_URL!

async function getToken(): Promise<string | null> {
  const { auth } = await import("@/auth")
  const session = await auth()
  if (!session) return null
  const token = (session as any).accessToken
  if (!token) return null
  const { encode } = await import("next-auth/jwt")
  return encode({
    token,
    secret: process.env.AUTH_SECRET ?? process.env.NEXTAUTH_SECRET!,
    salt: "authjs.session-token",
  })
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = await getToken()
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(error.detail || "API error")
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export type Workspace = {
  id: string
  name: string
  created_at: string
  updated_at: string
}

export const api = {
  workspaces: {
    list: () => apiFetch<Workspace[]>("/workspaces"),
    create: (name: string) =>
      apiFetch<Workspace>("/workspaces", {
        method: "POST",
        body: JSON.stringify({ name }),
      }),
    rename: (id: string, name: string) =>
      apiFetch<Workspace>(`/workspaces/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ name }),
      }),
    delete: (id: string) =>
      apiFetch<void>(`/workspaces/${id}`, { method: "DELETE" }),
  },
}