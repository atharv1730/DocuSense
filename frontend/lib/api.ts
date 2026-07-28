/**
 * API client for the backend.
 *
 * This file contains the API client for the backend.
 * It signs an HS256 JWT from the NextAuth session for backend auth.
 */
import { SignJWT } from "jose"

const API_URL = process.env.NEXT_PUBLIC_API_URL!

async function getToken(): Promise<string | null> {
  const { auth } = await import("@/auth")
  const session = await auth()
  if (!session) return null
  const claims = (session as any).accessToken
  if (!claims?.email) return null

  const secret = new TextEncoder().encode(
    process.env.AUTH_SECRET ?? process.env.NEXTAUTH_SECRET!
  )

  return new SignJWT({
    email: claims.email,
    name: claims.name,
    picture: claims.picture,
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("1h")
    .sign(secret)
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