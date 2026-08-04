"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { streamChat, type Citation } from "@/lib/api"

type Message = {
  role: "user" | "assistant"
  content: string
  citations?: Citation[]
  abstained?: boolean
  streaming?: boolean
  error?: string
}

export default function ChatPanel({
  workspaceId,
  authToken,
}: {
  workspaceId: string
  authToken: string
}) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null)
  const [rerankEnabled, setRerankEnabled] = useState(false)

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
      { query, rerank_enabled: rerankEnabled },
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
          <span style={{ width: 80 }} />
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
                    flexWrap: "wrap",
                    gap: 6,
                  }}
                >
                  {m.citations.map((c) => (
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
                      [{c.index}] {c.filename} · p.{c.page_number}
                    </button>
                  ))}
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
            justifyContent: "space-between",
            padding: "10px 0 0",
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
