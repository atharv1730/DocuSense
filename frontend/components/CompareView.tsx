"use client"

import { useState } from "react"
import Link from "next/link"
import type { Document, ComparisonResult, AlignedSection } from "@/lib/api"
import { compareDocuments } from "@/app/dashboard/actions"

function DocumentSelect({
  label,
  documents,
  value,
  onChange,
}: {
  label: string
  documents: Document[]
  value: string
  onChange: (id: string) => void
}) {
  return (
    <div style={{ flex: 1 }}>
      <label style={{ fontSize: 12, fontWeight: 500, color: "#666", display: "block", marginBottom: 4 }}>
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: "100%",
          padding: "8px 10px",
          border: "1px solid #ddd",
          borderRadius: 6,
          fontSize: 14,
          background: "#fff",
        }}
      >
        <option value="">Select a document…</option>
        {documents.map((doc) => (
          <option key={doc.id} value={doc.id}>
            {doc.filename}
            {!doc.chunking_strategies.includes("semantic") ? " (needs semantic chunking)" : ""}
          </option>
        ))}
      </select>
    </div>
  )
}

function DiffBadge({ section }: { section: AlignedSection }) {
  if (section.identical) {
    return (
      <span style={{ fontSize: 11, fontWeight: 600, color: "#16a34a", background: "#f0fdf4", border: "1px solid #dcfce7", borderRadius: 999, padding: "2px 8px" }}>
        Identical
      </span>
    )
  }
  return (
    <span style={{ fontSize: 11, fontWeight: 600, color: "#b45309", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 999, padding: "2px 8px" }}>
      Changed
    </span>
  )
}

function AlignedSectionRow({ section }: { section: AlignedSection }) {
  const [expanded, setExpanded] = useState(false)
  const hasDetails = section.differences.length > 0 || section.changed_clauses.length > 0

  return (
    <div style={{ border: "1px solid #eee", borderRadius: 8, background: "#fff", overflow: "hidden" }}>
      <div
        onClick={() => hasDetails && setExpanded((v) => !v)}
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 90px 1fr",
          alignItems: "center",
          gap: 12,
          padding: "12px 16px",
          cursor: hasDetails ? "pointer" : "default",
        }}
      >
        <div style={{ fontSize: 13 }}>
          <div style={{ fontWeight: 500 }}>{section.section_title.split(" / ")[0]}</div>
          {section.page_a != null && (
            <div style={{ fontSize: 11, color: "#999" }}>p.{section.page_a}</div>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
          <DiffBadge section={section} />
          {hasDetails && (
            <span style={{ fontSize: 10, color: "#999" }}>{expanded ? "Hide ▲" : "Details ▼"}</span>
          )}
        </div>
        <div style={{ fontSize: 13, textAlign: "right" }}>
          <div style={{ fontWeight: 500 }}>
            {section.section_title.includes(" / ") ? section.section_title.split(" / ")[1] : section.section_title}
          </div>
          {section.page_b != null && (
            <div style={{ fontSize: 11, color: "#999" }}>p.{section.page_b}</div>
          )}
        </div>
      </div>

      {expanded && hasDetails && (
        <div style={{ borderTop: "1px solid #f0f0f0", padding: "12px 16px", background: "#fafafa" }}>
          {section.differences.length > 0 && (
            <div style={{ marginBottom: section.changed_clauses.length > 0 ? 12 : 0 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#666", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.3 }}>
                Differences
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "#333" }}>
                {section.differences.map((d, i) => (
                  <li key={i} style={{ marginBottom: 4 }}>{d}</li>
                ))}
              </ul>
            </div>
          )}
          {section.changed_clauses.length > 0 && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#666", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.3 }}>
                Changed clauses
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "#333" }}>
                {section.changed_clauses.map((c, i) => (
                  <li key={i} style={{ marginBottom: 4 }}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function CompareView({
  workspaceId,
  initialDocuments,
}: {
  workspaceId: string
  initialDocuments: Document[]
}) {
  const readyDocuments = initialDocuments.filter((d) => d.status === "ready")

  const [docIdA, setDocIdA] = useState("")
  const [docIdB, setDocIdB] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ComparisonResult | null>(null)

  async function handleCompare() {
    if (!docIdA || !docIdB) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await compareDocuments(workspaceId, docIdA, docIdB)
      setResult(res)
    } catch (e: any) {
      setError(e.message || "Comparison failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 860, margin: "60px auto", padding: "0 16px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>Compare documents</h1>
        <Link
          href={`/dashboard/${workspaceId}`}
          style={{ fontSize: 13, fontWeight: 500, color: "#111", textDecoration: "none", border: "1px solid #ddd", borderRadius: 8, padding: "6px 12px" }}
        >
          ← Documents
        </Link>
      </div>

      {readyDocuments.length < 2 && (
        <p style={{ color: "#999", fontSize: 14, marginBottom: 16 }}>
          You need at least two fully processed documents in this workspace to compare them.
        </p>
      )}

      <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
        <DocumentSelect label="Document A" documents={readyDocuments} value={docIdA} onChange={setDocIdA} />
        <DocumentSelect label="Document B" documents={readyDocuments} value={docIdB} onChange={setDocIdB} />
      </div>

      <p style={{ fontSize: 12, color: "#999", marginTop: -8, marginBottom: 16 }}>
        Both documents must have semantic chunking run (see &ldquo;+ Add semantic chunks&rdquo; on the documents page).
        Comparison runs one model call per section and can take 30-60 seconds.
      </p>

      <button
        onClick={handleCompare}
        disabled={!docIdA || !docIdB || loading}
        style={{
          padding: "8px 16px",
          background: !docIdA || !docIdB || loading ? "#ccc" : "#111",
          color: "#fff",
          border: "none",
          borderRadius: 6,
          cursor: !docIdA || !docIdB || loading ? "default" : "pointer",
          fontSize: 14,
          marginBottom: 24,
        }}
      >
        {loading ? "Comparing… this can take up to a minute" : "Compare"}
      </button>

      {error && (
        <div style={{ color: "#dc2626", fontSize: 13, marginBottom: 24, padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8 }}>
          {error}
        </div>
      )}

      {loading && (
        <div style={{ color: "#888", fontSize: 13, padding: "16px 0" }}>
          Aligning sections and comparing content…
        </div>
      )}

      {result && (
        <>
          <div style={{ padding: "14px 16px", background: "#f5f5f5", borderRadius: 8, marginBottom: 20, fontSize: 13, color: "#333" }}>
            <strong>{result.aligned_sections.length}</strong> sections compared,{" "}
            <strong>{result.diff_count}</strong> difference{result.diff_count === 1 ? "" : "s"} found,{" "}
            <strong>{result.only_in_a.length}</strong> section{result.only_in_a.length === 1 ? "" : "s"} only in{" "}
            <strong>{result.document_a.filename}</strong>,{" "}
            <strong>{result.only_in_b.length}</strong> section{result.only_in_b.length === 1 ? "" : "s"} only in{" "}
            <strong>{result.document_b.filename}</strong>.
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 90px 1fr", gap: 12, padding: "0 16px", marginBottom: 8, fontSize: 12, fontWeight: 600, color: "#888", textTransform: "uppercase", letterSpacing: 0.3 }}>
            <div>{result.document_a.filename}</div>
            <div style={{ textAlign: "center" }}></div>
            <div style={{ textAlign: "right" }}>{result.document_b.filename}</div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 32 }}>
            {result.aligned_sections.length === 0 && (
              <p style={{ color: "#999", fontSize: 14 }}>No aligned sections found.</p>
            )}
            {result.aligned_sections.map((section, i) => (
              <AlignedSectionRow key={i} section={section} />
            ))}
          </div>

          {(result.only_in_a.length > 0 || result.only_in_b.length > 0) && (
            <div style={{ display: "flex", gap: 24 }}>
              <div style={{ flex: 1 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>
                  Only in {result.document_a.filename}
                </h3>
                {result.only_in_a.length === 0 ? (
                  <p style={{ color: "#999", fontSize: 13 }}>None.</p>
                ) : (
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                    {result.only_in_a.map((s, i) => (
                      <li key={i} style={{ marginBottom: 4 }}>
                        {s.section_title}
                        {s.page_number != null && <span style={{ color: "#999" }}> (p.{s.page_number})</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div style={{ flex: 1 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>
                  Only in {result.document_b.filename}
                </h3>
                {result.only_in_b.length === 0 ? (
                  <p style={{ color: "#999", fontSize: 13 }}>None.</p>
                ) : (
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                    {result.only_in_b.map((s, i) => (
                      <li key={i} style={{ marginBottom: 4 }}>
                        {s.section_title}
                        {s.page_number != null && <span style={{ color: "#999" }}> (p.{s.page_number})</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
