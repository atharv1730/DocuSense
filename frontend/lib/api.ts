/**
 * API client for the backend.
 *
 * This file contains the API client for the backend.
 * It signs an HS256 JWT from the NextAuth session for backend auth.
 */
import { SignJWT } from "jose"

const API_URL = process.env.NEXT_PUBLIC_API_URL!

/**
 * Server-only: mints the short-lived backend JWT from the current
 * NextAuth session. Exported so Server Components (e.g. the chat page)
 * can pass it down as a prop to Client Components, which cannot import
 * "@/auth" themselves.
 */
export async function getAuthToken(): Promise<string | null> {
  return getToken()
}

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
  const isFormData =
    typeof FormData !== "undefined" && options.body instanceof FormData
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
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

export type Document = {
  id: string
  workspace_id: string
  filename: string
  page_count: number | null
  size_bytes: number | null
  status: "uploaded" | "extracting" | "chunking" | "embedding" | "ready" | "failed"
  error_message: string | null
  chunking_strategies: string[]
  created_at: string
  updated_at: string
}

export type Citation = {
  index: number
  filename: string
  page_number: number
  text: string
}

export type ChatTokenEvent = {
  type: "token"
  text: string
}

export type RatableChunk = {
  id: string
  filename: string
  page_number: number
  text: string
}

export type ChatDoneEvent = {
  type: "done"
  answer: string
  citations: Citation[]
  abstained: boolean
  retrieval_log_id: string | null
  chunks: RatableChunk[]
}

export type ChatErrorEvent = {
  type: "error"
  message: string
}

export type ChatRequestBody = {
  query: string
  document_id?: string
  chunking_strategy?: string
  rerank_enabled?: boolean
}

/**
 * Streams a chat response over SSE. Uses fetch() + a ReadableStream reader
 * instead of EventSource because EventSource only supports GET requests,
 * and we need to POST the query body.
 *
 * Returns an abort function the caller should invoke on unmount / cleanup.
 */
export function streamChat(
  workspaceId: string,
  body: ChatRequestBody,
  token: string,
  onToken: (text: string) => void,
  onDone: (event: ChatDoneEvent) => void,
  onError: (message: string) => void
): () => void {
  const controller = new AbortController()

  ;(async () => {
    try {
      const res = await fetch(`${API_URL}/workspaces/${workspaceId}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!res.ok || !res.body) {
        const errBody = await res.json().catch(() => null)
        onError(errBody?.detail || `Request failed (${res.status})`)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        // Last element may be an incomplete line split across chunks.
        buffer = lines.pop() ?? ""

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          const jsonStr = line.slice("data: ".length)
          if (!jsonStr) continue

          let event: ChatTokenEvent | ChatDoneEvent | ChatErrorEvent
          try {
            event = JSON.parse(jsonStr)
          } catch {
            continue
          }

          if (event.type === "token") onToken(event.text)
          else if (event.type === "done") onDone(event)
          else if (event.type === "error") onError(event.message)
        }
      }
    } catch (e: any) {
      if (e?.name === "AbortError") return
      onError(e?.message || "Connection lost")
    }
  })()

  return () => controller.abort()
}

export type ConfigMetrics = {
  chunking_strategy: string
  rerank_enabled: boolean
  precision_at_1: number | null
  precision_at_3: number | null
  precision_at_5: number | null
  mrr: number | null
  query_count: number
  rated_query_count: number
  coverage: number
}

export type MetricsResponse = {
  configs: ConfigMetrics[]
  overall_coverage: number
}

export type ChunkRatingOut = {
  chunk_id: string
  rating: number
}

export type RetrievalLogOut = {
  id: string
  conversation_id: string | null
  query: string
  chunking_strategy: string | null
  rerank_enabled: boolean
  is_replay: boolean
  stage1_chunk_ids: string[] | null
  stage2_chunk_ids: string[] | null
  final_chunk_ids: string[] | null
  answer: string | null
  abstained: boolean | null
  created_at: string
  ratings: ChunkRatingOut[]
}

export type ChunkPreview = {
  id: string
  filename: string
  page_number: number | null
  text: string
}

export type RetrievalLogsResponse = {
  logs: RetrievalLogOut[]
  total: number
  page: number
  page_size: number
  chunk_previews: Record<string, ChunkPreview>
}

export type ReplayResponse = {
  log_ids: string[]
}

/**
 * Client-safe rating submission. Like streamChat, this takes an
 * already-minted token as a prop instead of calling the server-only
 * getToken(), since it's invoked from a Client Component (ChatPanel).
 */
export async function submitChunkRating(
  workspaceId: string,
  token: string,
  retrievalLogId: string,
  ratings: { chunk_id: string; rating: number }[]
): Promise<void> {
  const res = await fetch(`${API_URL}/workspaces/${workspaceId}/eval/ratings`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ retrieval_log_id: retrievalLogId, ratings }),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(error.detail || "Failed to submit rating")
  }
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
  documents: {
    list: (workspaceId: string) =>
      apiFetch<Document[]>(`/workspaces/${workspaceId}/documents`),
    upload: (workspaceId: string, file: File) => {
      const form = new FormData()
      form.append("file", file)
      return apiFetch<Document>(`/workspaces/${workspaceId}/documents`, {
        method: "POST",
        body: form,
        headers: {}, // let browser set multipart boundary
      })
    },
    delete: (workspaceId: string, documentId: string) =>
      apiFetch<void>(`/workspaces/${workspaceId}/documents/${documentId}`, {
        method: "DELETE",
      }),
    rechunk: (workspaceId: string, documentId: string, strategy: string) =>
      apiFetch<{ status: string }>(
        `/workspaces/${workspaceId}/documents/${documentId}/rechunk`,
        {
          method: "POST",
          body: JSON.stringify({ strategy }),
        }
      ),
  },
  eval: {
    metrics: (workspaceId: string) =>
      apiFetch<MetricsResponse>(`/workspaces/${workspaceId}/eval/metrics`),
    submitRatings: (
      workspaceId: string,
      retrievalLogId: string,
      ratings: { chunk_id: string; rating: number }[]
    ) =>
      apiFetch<void>(`/workspaces/${workspaceId}/eval/ratings`, {
        method: "POST",
        body: JSON.stringify({ retrieval_log_id: retrievalLogId, ratings }),
      }),
    logs: (
      workspaceId: string,
      params: {
        page?: number
        page_size?: number
        chunking_strategy?: string
        rerank?: boolean
      } = {}
    ) => {
      const search = new URLSearchParams()
      if (params.page) search.set("page", String(params.page))
      if (params.page_size) search.set("page_size", String(params.page_size))
      if (params.chunking_strategy) search.set("chunking_strategy", params.chunking_strategy)
      if (params.rerank !== undefined) search.set("rerank", String(params.rerank))
      const qs = search.toString()
      return apiFetch<RetrievalLogsResponse>(
        `/workspaces/${workspaceId}/eval/logs${qs ? `?${qs}` : ""}`
      )
    },
    replay: (
      workspaceId: string,
      logIds: string[],
      chunkingStrategy: string,
      rerankEnabled: boolean
    ) =>
      apiFetch<ReplayResponse>(`/workspaces/${workspaceId}/eval/replay`, {
        method: "POST",
        body: JSON.stringify({
          log_ids: logIds,
          chunking_strategy: chunkingStrategy,
          rerank_enabled: rerankEnabled,
        }),
      }),
  },
}
