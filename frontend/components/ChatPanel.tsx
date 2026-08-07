"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import {
  streamChat,
  submitChunkRating,
  type Citation,
  type Document,
  type RatableChunk,
} from "@/lib/api"

type Message = {
  role: "user" | "assistant"
  content: string
  citations?: Citation[]
  abstained?: boolean
  streaming?: boolean
  error?: string
  retrievalLogId?: string | null
  chunks?: RatableChunk[]
  ratings?: Record<string, 0 | 1>
}

const ALL_DOCUMENTS = "__all__"

function groupCitationsByDocument(
  citations: Citation[]
): { filename: string; citations: Citation[] }[] {
  const groups: { filename: string; citations: Citation[] }[] = []
  for (const c of citations) {
    const existing = groups.find((g) => g.filename === c.filename)
    if (existing) existing.citations.push(c)
    else groups.push({ filename: c.filename, citations: [c] })
  }
  return groups
}

export default function ChatPanel({
  workspaceId,
  authToken,
  initialDocuments,
}: {
  workspaceId: string
  authToken: string
  initialDocuments: Document[]
}) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null)
  const [rerankEnabled, setRerankEnabled] = useState(false)
  const [documents] = useState<Document[]>(
    initialDocuments.filter((d) => d.status === "ready")
  )
  const [scopeDocumentId, setScopeDocumentId] = useState<string>(ALL_DOCUMENTS)
  const [chunkingStrategy, setChunkingStrategy] = useState<"fixed" | "semantic">("fixed")

  // Semantic retrieval requires every in-scope document to have semantic
  // chunks. When scoped to "All documents", that means every ready doc;
  // when scoped to one document, just that document.
  const semanticAvailable =
    scopeDocumentId === ALL_DOCUMENTS
      ? documents.length > 0 &&
        documents.every((d) => d.chunking_strategies.includes("semantic"))
      : documents.find((d) => d.id === scopeDocumentId)?.chunking_strategies.includes("semantic") ?? false

  useEffect(() => {
    if (!semanticAvailable && chunkingStrategy === "semantic") {
      setChunkingStrategy("fixed")
    }
  }, [semanticAvailable, chunkingStrategy])

  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  useEffect(() => {
    return () => {
      abortRef.current?.()
    }
  }, [])

  function updateLastAssistant(update: Partial<Message>) {
    setMessages((prev) => {
      const next = [...prev]
      const lastIdx = next.length - 1
      if (lastIdx >= 0 && next[lastIdx].role === "assistant") {
        next[lastIdx] = { ...next[lastIdx], ...update }
      }
      return next
    })
  }

  function appendToLastAssistant(text: string) {
    setMessages((prev) => {
      const next = [...prev]
      const lastIdx = next.length - 1
      if (lastIdx >= 0 && next[lastIdx].role === "assistant") {
        next[lastIdx] = {
          ...next[lastIdx],
          content: next[lastIdx].content + text,
        }
      }
      return next
    })
  }

  function handleSend() {
    const query = input.trim()
    if (!query || loading) return

    setInput("")
    setLoading(true)
    setSelectedCitation(null)
    setMessages((prev) => [
      ...prev,
      { role: "user", content: query },
      { role: "assistant", content: "", streaming: true },
    ])

    const abort = streamChat(
      workspaceId,
      {
        query,
        rerank_enabled: rerankEnabled,
        chunking_strategy: chunkingStrategy,
        document_id: scopeDocumentId === ALL_DOCUMENTS ? undefined : scopeDocumentId,
      },
      authToken,
      (text) => {
        appendToLastAssistant(text)
      },
      (event) => {
        updateLastAssistant({
          content: event.answer,
          citations: event.citations,
          abstained: event.abstained,
          streaming: false,
          retrievalLogId: event.retrieval_log_id,
          chunks: event.chunks,
          ratings: {},
        })
        setLoading(false)
      },
      (message) => {
        updateLastAssistant({
          streaming: false,
          error: message,
        })
        setLoading(false)
      }
    )
    abortRef.current = abort
  }

  function handleRate(messageIndex: number, chunkId: string, rating: 0 | 1) {
    const message = messages[messageIndex]
    if (!message?.retrievalLogId) return

    setMessages((prev) => {
      const next = [...prev]
      const target = next[messageIndex]
      next[messageIndex] = {
        ...target,
        ratings: { ...target.ratings, [chunkId]: rating },
      }
      return next
    })

    submitChunkRating(workspaceId, authToken, message.retrievalLogId, [
      { chunk_id: chunkId, rating },
    ]).catch(() => {
      // Best-effort: revert the optimistic highlight if the save failed.
      setMessages((prev) => {
        const next = [...prev]
        const target = next[messageIndex]
        const ratings = { ...target.ratings }
        delete ratings[chunkId]
        next[messageIndex] = { ...target, ratings }
        return next
      })
    })
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
      }}
    >
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          maxWidth: 760,
          margin: "0 auto",
          padding: "0 16px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "20px 0 12px",
            borderBottom: "1px solid #eee",
          }}
        >
          <Link
            href={`/dashboard/${workspaceId}`}
            style={{ fontSize: 13, color: "#888", textDecoration: "none" }}
          >
            ← Documents
          </Link>
          <h1 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Chat</h1>
          <div style={{ display: "flex", gap: 12 }}>
            <Link
              href={`/dashboard/${workspaceId}/compare`}
              style={{ fontSize: 13, color: "#888", textDecoration: "none" }}
            >
              Compare
            </Link>
            <Link
              href={`/dashboard/${workspaceId}/eval`}
              style={{ fontSize: 13, color: "#888", textDecoration: "none" }}
            >
              Eval dashboard →
            </Link>
          </div>
        </div>

        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "16px 0",
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          {messages.length === 0 && (
            <p style={{ color: "#999", fontSize: 14, marginTop: 40, textAlign: "center" }}>
              Ask a question about your documents.
            </p>
          )}

          {messages.map((m, i) => (
            <div key={i} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div
                style={{
                  alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                  maxWidth: "85%",
                  padding: "10px 14px",
                  borderRadius: 12,
                  background: m.role === "user" ? "#111" : "#f4f4f5",
                  color: m.role === "user" ? "#fff" : "#111",
                  fontSize: 14,
                  lineHeight: 1.5,
                  whiteSpace: "pre-wrap",
                }}
              >
                {m.content}
                {m.streaming && <span style={{ opacity: 0.5 }}>▌</span>}
                {m.error && (
                  <div style={{ color: "#dc2626", fontSize: 13, marginTop: 6 }}>
                    ⚠ {m.error}
                  </div>
                )}
              </div>

              {m.role === "assistant" && m.abstained && !m.streaming && (
                <div
                  style={{
                    alignSelf: "flex-start",
                    fontSize: 12,
                    color: "#b45309",
                    background: "#fffbeb",
                    border: "1px solid #fde68a",
                    borderRadius: 6,
                    padding: "4px 8px",
                  }}
                >
                  No answer found in your documents
                </div>
              )}

              {m.role === "assistant" && !!m.citations?.length && !m.streaming && (
                <div
                  style={{
                    alignSelf: "flex-start",
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                  }}
                >
                  {groupCitationsByDocument(m.citations).map((group) => (
                    <div key={group.filename} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
                      <span style={{ fontSize: 11, color: "#999", fontWeight: 500 }}>
                        {group.filename}:
                      </span>
                      {group.citations.map((c) => (
                        <button
                          key={c.index}
                          onClick={() =>
                            setSelectedCitation(
                              selectedCitation?.index === c.index &&
                                selectedCitation?.filename === c.filename
                                ? null
                                : c
                            )
                          }
                          style={{
                            fontSize: 12,
                            padding: "3px 8px",
                            borderRadius: 999,
                            border: "1px solid #ddd",
                            background:
                              selectedCitation?.index === c.index &&
                              selectedCitation?.filename === c.filename
                                ? "#111"
                                : "#fff",
                            color:
                              selectedCitation?.index === c.index &&
                              selectedCitation?.filename === c.filename
                                ? "#fff"
                                : "#333",
                            cursor: "pointer",
                          }}
                        >
                          [{c.index}] p.{c.page_number}
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              )}

              {m.role === "assistant" &&
                !m.streaming &&
                !m.abstained &&
                !!m.chunks?.length &&
                m.retrievalLogId && (
                  <div
                    style={{
                      alignSelf: "flex-start",
                      display: "flex",
                      flexDirection: "column",
                      gap: 6,
                      width: "100%",
                      maxWidth: "85%",
                    }}
                  >
                    <span style={{ fontSize: 11, color: "#999" }}>
                      Rate retrieved chunks:
                    </span>
                    {m.chunks.map((chunk) => {
                      const rating = m.ratings?.[chunk.id]
                      return (
                        <div
                          key={chunk.id}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            padding: "6px 10px",
                            border: "1px solid #eee",
                            borderRadius: 8,
                            background: "#fafafa",
                          }}
                        >
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 11, color: "#999" }}>
                              {chunk.filename} · p.{chunk.page_number}
                            </div>
                            <div
                              style={{
                                fontSize: 12,
                                color: "#444",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {chunk.text}
                            </div>
                          </div>
                          <button
                            onClick={() => handleRate(i, chunk.id, 1)}
                            title="Relevant"
                            style={{
                              fontSize: 14,
                              padding: "4px 8px",
                              borderRadius: 6,
                              border: "1px solid #ddd",
                              background: rating === 1 ? "#16a34a" : "#fff",
                              color: rating === 1 ? "#fff" : "#333",
                              cursor: "pointer",
                            }}
                          >
                            👍
                          </button>
                          <button
                            onClick={() => handleRate(i, chunk.id, 0)}
                            title="Not relevant"
                            style={{
                              fontSize: 14,
                              padding: "4px 8px",
                              borderRadius: 6,
                              border: "1px solid #ddd",
                              background: rating === 0 ? "#dc2626" : "#fff",
                              color: rating === 0 ? "#fff" : "#333",
                              cursor: "pointer",
                            }}
                          >
                            👎
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}
            </div>
          ))}

          {selectedCitation && (
            <div
              style={{
                border: "1px solid #eee",
                borderRadius: 10,
                padding: "12px 16px",
                background: "#fafafa",
                fontSize: 13,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <strong>
                  {selectedCitation.filename} · page {selectedCitation.page_number}
                </strong>
                <button
                  onClick={() => setSelectedCitation(null)}
                  style={{ border: "none", background: "none", cursor: "pointer", color: "#888" }}
                >
                  ✕
                </button>
              </div>
              <p style={{ color: "#555", lineHeight: 1.5 }}>{selectedCitation.text}</p>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "10px 0 0",
          }}
        >
          <span style={{ fontSize: 12, color: "#666" }}>Scope:</span>
          <select
            value={scopeDocumentId}
            onChange={(e) => setScopeDocumentId(e.target.value)}
            style={{
              fontSize: 12,
              padding: "4px 8px",
              borderRadius: 6,
              border: "1px solid #ddd",
              background: "#fff",
              color: "#333",
            }}
          >
            <option value={ALL_DOCUMENTS}>All documents</option>
            {documents.map((doc) => (
              <option key={doc.id} value={doc.id}>
                {doc.filename}
              </option>
            ))}
          </select>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "8px 0 0",
          }}
        >
          <span style={{ fontSize: 12, color: "#666" }}>Chunking:</span>
          <select
            value={chunkingStrategy}
            onChange={(e) => setChunkingStrategy(e.target.value as "fixed" | "semantic")}
            style={{
              fontSize: 12,
              padding: "4px 8px",
              borderRadius: 6,
              border: "1px solid #ddd",
              background: "#fff",
              color: "#333",
            }}
          >
            <option value="fixed">Fixed chunking</option>
            <option value="semantic" disabled={!semanticAvailable}>
              Semantic chunking{!semanticAvailable ? " (not available)" : ""}
            </option>
          </select>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "6px 0 0",
          }}
        >
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 12,
              color: "#666",
              cursor: "pointer",
              userSelect: "none",
            }}
          >
            <span
              onClick={() => setRerankEnabled((v) => !v)}
              role="switch"
              aria-checked={rerankEnabled}
              style={{
                position: "relative",
                width: 32,
                height: 18,
                borderRadius: 999,
                background: rerankEnabled ? "#111" : "#ddd",
                transition: "background 0.15s",
                display: "inline-block",
              }}
            >
              <span
                style={{
                  position: "absolute",
                  top: 2,
                  left: rerankEnabled ? 16 : 2,
                  width: 14,
                  height: 14,
                  borderRadius: "50%",
                  background: "#fff",
                  transition: "left 0.15s",
                }}
              />
            </span>
            Re-ranking
          </label>
          <span style={{ fontSize: 11, color: "#999" }}>
            {rerankEnabled ? "Cross-encoder re-ranking is ON" : "Re-ranking is OFF (top-k by similarity)"}
          </span>
        </div>

        <div
          style={{
            display: "flex",
            gap: 8,
            padding: "8px 0 20px",
            borderTop: "1px solid #eee",
          }}
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your documents..."
            rows={1}
            style={{
              flex: 1,
              resize: "none",
              padding: "10px 12px",
              borderRadius: 8,
              border: "1px solid #ddd",
              fontSize: 14,
              fontFamily: "inherit",
            }}
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            style={{
              padding: "0 18px",
              borderRadius: 8,
              border: "none",
              background: loading || !input.trim() ? "#ccc" : "#111",
              color: "#fff",
              fontSize: 14,
              cursor: loading || !input.trim() ? "default" : "pointer",
            }}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
