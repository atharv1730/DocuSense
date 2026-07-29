"use client"

import { useState, useEffect, useRef } from "react"
import { api, Document } from "@/lib/api"

const STATUS_COLORS: Record<string, string> = {
  uploaded: "#888",
  extracting: "#f59e0b",
  chunking: "#f59e0b",
  embedding: "#f59e0b",
  ready: "#16a34a",
  failed: "#dc2626",
}

const STATUS_LABELS: Record<string, string> = {
  uploaded: "Queued",
  extracting: "Extracting text...",
  chunking: "Chunking...",
  embedding: "Embedding...",
  ready: "Ready",
  failed: "Failed",
}

export default function DocumentsPanel({
  workspaceId,
  initialDocuments,
}: {
  workspaceId: string
  initialDocuments: Document[]
}) {
  const [documents, setDocuments] = useState(initialDocuments)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pollingRef = useRef<NodeJS.Timeout | null>(null)

  // Poll status for in-progress documents
  useEffect(() => {
    const inProgress = documents.some(
      (d) => !["ready", "failed"].includes(d.status)
    )

    if (inProgress) {
      pollingRef.current = setInterval(async () => {
        const updated = await api.documents.list(workspaceId)
        setDocuments(updated)
      }, 2000)
    }

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [documents, workspaceId])

  async function handleUpload(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported")
      return
    }
    setError(null)
    setUploading(true)
    try {
      const doc = await api.documents.upload(workspaceId, file)
      setDocuments((prev) => [doc, ...prev])
    } catch (e: any) {
      setError(e.message)
    } finally {
      setUploading(false)
    }
  }

  async function handleDelete(docId: string) {
    await api.documents.delete(workspaceId, docId)
    setDocuments((prev) => prev.filter((d) => d.id !== docId))
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleUpload(file)
  }

  return (
    <div style={{ maxWidth: 640, margin: "60px auto", padding: "0 16px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>Documents</h1>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => fileInputRef.current?.click()}
        style={{
          border: "2px dashed #ddd",
          borderRadius: 10,
          padding: "32px 16px",
          textAlign: "center",
          cursor: "pointer",
          marginBottom: 24,
          color: "#888",
          fontSize: 14,
        }}
      >
        {uploading ? "Uploading..." : "Drop a PDF here or click to upload"}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleUpload(file)
          }}
        />
      </div>

      {error && (
        <p style={{ color: "#dc2626", fontSize: 13, marginBottom: 16 }}>{error}</p>
      )}

      {documents.length === 0 && (
        <p style={{ color: "#999", fontSize: 14 }}>No documents yet.</p>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {documents.map((doc) => (
          <div
            key={doc.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "12px 16px",
              border: "1px solid #eee",
              borderRadius: 8,
              background: "#fff",
            }}
          >
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 500 }}>{doc.filename}</div>
              <div style={{ fontSize: 12, color: "#888", marginTop: 2 }}>
                {doc.page_count ? `${doc.page_count} pages · ` : ""}
                {doc.size_bytes ? `${(doc.size_bytes / 1024).toFixed(0)} KB` : ""}
              </div>
              {doc.error_message && (
                <div style={{ fontSize: 11, color: "#dc2626", marginTop: 4 }}>
                  {doc.error_message}
                </div>
              )}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{
                fontSize: 11,
                fontWeight: 500,
                color: STATUS_COLORS[doc.status] || "#888",
              }}>
                {STATUS_LABELS[doc.status] || doc.status}
              </span>
              {doc.status === "ready" && (
                <button
                  onClick={() => handleDelete(doc.id)}
                  style={{
                    fontSize: 12,
                    color: "#c00",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                  }}
                >
                  Delete
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}