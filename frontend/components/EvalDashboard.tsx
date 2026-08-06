"use client"

import { useState } from "react"
import Link from "next/link"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type {
  ChunkPreview,
  ConfigMetrics,
  MetricsResponse,
  RetrievalLogOut,
  RetrievalLogsResponse,
} from "@/lib/api"
import { getEvalLogs, getEvalMetrics, replayEvalQueries } from "@/app/dashboard/actions"

const PAGE_SIZE = 20

function configLabel(c: { chunking_strategy: string; rerank_enabled: boolean }): string {
  return `${c.chunking_strategy} / rerank ${c.rerank_enabled ? "on" : "off"}`
}

function pct(n: number | null): string {
  return n === null ? "—" : `${(n * 100).toFixed(0)}%`
}

function ratingBadge(rating: number | undefined) {
  if (rating === undefined) {
    return <span style={{ fontSize: 11, color: "#bbb" }}>unrated</span>
  }
  return rating === 1 ? (
    <span style={{ fontSize: 12 }}>👍</span>
  ) : (
    <span style={{ fontSize: 12 }}>👎</span>
  )
}

function ChunkList({
  chunkIds,
  ratings,
  previews,
}: {
  chunkIds: string[] | null
  ratings: Record<string, number>
  previews: Record<string, ChunkPreview>
}) {
  if (!chunkIds || chunkIds.length === 0) {
    return <p style={{ fontSize: 12, color: "#999" }}>No data</p>
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {chunkIds.map((id, idx) => {
        const preview = previews[id]
        return (
          <div
            key={id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 8px",
              border: "1px solid #eee",
              borderRadius: 6,
              background: "#fff",
              fontSize: 12,
            }}
          >
            <span style={{ color: "#999", width: 16 }}>{idx + 1}.</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              {preview ? (
                <>
                  <div style={{ color: "#999", fontSize: 10 }}>
                    {preview.filename} · p.{preview.page_number ?? "?"}
                  </div>
                  <div
                    style={{
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      color: "#444",
                    }}
                  >
                    {preview.text}
                  </div>
                </>
              ) : (
                <span style={{ color: "#bbb" }}>{id.slice(0, 8)}…</span>
              )}
            </div>
            {ratingBadge(ratings[id])}
          </div>
        )
      })}
    </div>
  )
}

export default function EvalDashboard({
  workspaceId,
  initialMetrics,
  initialLogs,
}: {
  workspaceId: string
  initialMetrics: MetricsResponse
  initialLogs: RetrievalLogsResponse
}) {
  const [metrics, setMetrics] = useState<MetricsResponse>(initialMetrics)
  const [logsData, setLogsData] = useState<RetrievalLogsResponse>(initialLogs)
  const [page, setPage] = useState(1)
  const [strategyFilter, setStrategyFilter] = useState("")
  const [rerankFilter, setRerankFilter] = useState("")
  const [loadingLogs, setLoadingLogs] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [replayStrategy, setReplayStrategy] = useState<"fixed" | "semantic">("fixed")
  const [replayRerank, setReplayRerank] = useState(false)
  const [replaying, setReplaying] = useState(false)
  const [replayMessage, setReplayMessage] = useState<string | null>(null)

  async function refreshLogs(nextPage: number, strategy: string, rerank: string) {
    setLoadingLogs(true)
    try {
      const data = await getEvalLogs(workspaceId, {
        page: nextPage,
        page_size: PAGE_SIZE,
        chunking_strategy: strategy || undefined,
        rerank: rerank === "" ? undefined : rerank === "true",
      })
      setLogsData(data)
      setPage(nextPage)
    } finally {
      setLoadingLogs(false)
    }
  }

  async function refreshMetrics() {
    const data = await getEvalMetrics(workspaceId)
    setMetrics(data)
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleReplay() {
    if (selectedIds.size === 0) return
    setReplaying(true)
    setReplayMessage(null)
    try {
      const result = await replayEvalQueries(
        workspaceId,
        Array.from(selectedIds),
        replayStrategy,
        replayRerank
      )
      setReplayMessage(
        `Replayed ${result.log_ids.length} quer${result.log_ids.length === 1 ? "y" : "ies"} under ${replayStrategy} / rerank ${replayRerank ? "on" : "off"}. Metrics below now include the new results.`
      )
      setSelectedIds(new Set())
      await Promise.all([refreshMetrics(), refreshLogs(1, strategyFilter, rerankFilter)])
    } catch (e) {
      setReplayMessage(e instanceof Error ? e.message : "Replay failed")
    } finally {
      setReplaying(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(logsData.total / logsData.page_size))

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "24px 16px 60px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 24,
        }}
      >
        <div>
          <Link
            href={`/dashboard/${workspaceId}`}
            style={{ fontSize: 13, color: "#888", textDecoration: "none" }}
          >
            ← Documents
          </Link>
          <h1 style={{ fontSize: 22, fontWeight: 600, margin: "6px 0 0" }}>
            Eval dashboard
          </h1>
        </div>
        <Link
          href={`/dashboard/${workspaceId}/chat`}
          style={{
            fontSize: 13,
            fontWeight: 500,
            color: "#111",
            textDecoration: "none",
            border: "1px solid #ddd",
            borderRadius: 8,
            padding: "6px 12px",
          }}
        >
          Open chat →
        </Link>
      </div>

      {/* Section A: metric cards + chart */}
      <section style={{ marginBottom: 40 }}>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            marginBottom: 12,
          }}
        >
          <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>
            Metrics by configuration
          </h2>
          <span style={{ fontSize: 12, color: "#888" }}>
            Overall coverage: {pct(metrics.overall_coverage)} of queries fully rated
          </span>
        </div>

        {metrics.configs.length === 0 ? (
          <div
            style={{
              border: "1px dashed #ddd",
              borderRadius: 10,
              padding: "32px 16px",
              textAlign: "center",
              color: "#999",
              fontSize: 14,
            }}
          >
            Ask questions and rate the results to see metrics.
          </div>
        ) : (
          <>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: 12,
                marginBottom: 20,
              }}
            >
              {metrics.configs.map((c) => (
                <MetricCard key={configLabel(c)} config={c} />
              ))}
            </div>

            <div style={{ width: "100%", height: 280 }}>
              <ResponsiveContainer>
                <BarChart data={metrics.configs.map((c) => ({
                  name: configLabel(c),
                  "precision@1": c.precision_at_1 ?? 0,
                  "precision@3": c.precision_at_3 ?? 0,
                  "precision@5": c.precision_at_5 ?? 0,
                  mrr: c.mrr ?? 0,
                }))}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="precision@1" fill="#6366f1" />
                  <Bar dataKey="precision@3" fill="#8b5cf6" />
                  <Bar dataKey="precision@5" fill="#a855f7" />
                  <Bar dataKey="mrr" fill="#111827" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </section>

      {/* Section C: replay panel */}
      <section
        style={{
          marginBottom: 40,
          border: "1px solid #eee",
          borderRadius: 10,
          padding: 16,
          background: "#fafafa",
        }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 600, margin: "0 0 8px" }}>
          Replay queries under a new configuration
        </h2>
        <p style={{ fontSize: 12, color: "#888", margin: "0 0 12px" }}>
          Select rows in the query log below, choose a target configuration, then replay.
          This re-runs retrieval only (no LLM call) and writes new log rows for a controlled
          A/B comparison.
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span style={{ fontSize: 12, color: "#666" }}>
            {selectedIds.size} quer{selectedIds.size === 1 ? "y" : "ies"} selected
          </span>
          <select
            value={replayStrategy}
            onChange={(e) => setReplayStrategy(e.target.value as "fixed" | "semantic")}
            style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid #ddd" }}
          >
            <option value="fixed">Fixed chunking</option>
            <option value="semantic">Semantic chunking</option>
          </select>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#666" }}>
            <input
              type="checkbox"
              checked={replayRerank}
              onChange={(e) => setReplayRerank(e.target.checked)}
            />
            Re-ranking on
          </label>
          <button
            onClick={handleReplay}
            disabled={selectedIds.size === 0 || replaying}
            style={{
              fontSize: 12,
              fontWeight: 500,
              padding: "6px 14px",
              borderRadius: 8,
              border: "none",
              background: selectedIds.size === 0 || replaying ? "#ccc" : "#111",
              color: "#fff",
              cursor: selectedIds.size === 0 || replaying ? "default" : "pointer",
            }}
          >
            {replaying ? "Replaying..." : "Replay retrieval"}
          </button>
        </div>
        {replayMessage && (
          <p style={{ fontSize: 12, color: "#166534", marginTop: 10 }}>{replayMessage}</p>
        )}
      </section>

      {/* Section B: query log table */}
      <section>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 12,
            flexWrap: "wrap",
            gap: 8,
          }}
        >
          <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Query log</h2>
          <div style={{ display: "flex", gap: 8 }}>
            <select
              value={strategyFilter}
              onChange={(e) => {
                setStrategyFilter(e.target.value)
                refreshLogs(1, e.target.value, rerankFilter)
              }}
              style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid #ddd" }}
            >
              <option value="">All strategies</option>
              <option value="fixed">Fixed</option>
              <option value="semantic">Semantic</option>
            </select>
            <select
              value={rerankFilter}
              onChange={(e) => {
                setRerankFilter(e.target.value)
                refreshLogs(1, strategyFilter, e.target.value)
              }}
              style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid #ddd" }}
            >
              <option value="">Rerank: any</option>
              <option value="true">Rerank: on</option>
              <option value="false">Rerank: off</option>
            </select>
          </div>
        </div>

        {logsData.logs.length === 0 ? (
          <div
            style={{
              border: "1px dashed #ddd",
              borderRadius: 10,
              padding: "32px 16px",
              textAlign: "center",
              color: "#999",
              fontSize: 14,
            }}
          >
            No queries logged yet. Ask a question in chat first.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {logsData.logs.map((log) => (
              <LogRow
                key={log.id}
                log={log}
                previews={logsData.chunk_previews}
                selected={selectedIds.has(log.id)}
                expanded={expandedId === log.id}
                onToggleSelect={() => toggleSelect(log.id)}
                onToggleExpand={() =>
                  setExpandedId((prev) => (prev === log.id ? null : log.id))
                }
              />
            ))}
          </div>
        )}

        {logsData.logs.length > 0 && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 12,
              marginTop: 16,
            }}
          >
            <button
              onClick={() => refreshLogs(page - 1, strategyFilter, rerankFilter)}
              disabled={page <= 1 || loadingLogs}
              style={{
                fontSize: 12,
                padding: "4px 10px",
                borderRadius: 6,
                border: "1px solid #ddd",
                background: "#fff",
                cursor: page <= 1 || loadingLogs ? "default" : "pointer",
                opacity: page <= 1 ? 0.5 : 1,
              }}
            >
              ← Prev
            </button>
            <span style={{ fontSize: 12, color: "#888" }}>
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => refreshLogs(page + 1, strategyFilter, rerankFilter)}
              disabled={page >= totalPages || loadingLogs}
              style={{
                fontSize: 12,
                padding: "4px 10px",
                borderRadius: 6,
                border: "1px solid #ddd",
                background: "#fff",
                cursor: page >= totalPages || loadingLogs ? "default" : "pointer",
                opacity: page >= totalPages ? 0.5 : 1,
              }}
            >
              Next →
            </button>
          </div>
        )}
      </section>
    </div>
  )
}

function MetricCard({ config: c }: { config: ConfigMetrics }) {
  return (
    <div
      style={{
        border: "1px solid #eee",
        borderRadius: 10,
        padding: 14,
        background: "#fff",
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 600, color: "#111", marginBottom: 8 }}>
        {configLabel(c)}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 12 }}>
        <Stat label="Precision@1" value={pct(c.precision_at_1)} />
        <Stat label="Precision@3" value={pct(c.precision_at_3)} />
        <Stat label="Precision@5" value={pct(c.precision_at_5)} />
        <Stat label="MRR" value={c.mrr === null ? "—" : c.mrr.toFixed(3)} />
      </div>
      <div style={{ marginTop: 8, fontSize: 11, color: "#999" }}>
        {c.query_count} queries · {c.rated_query_count} rated · {pct(c.coverage)} fully-rated
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ color: "#999", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.3 }}>
        {label}
      </div>
      <div style={{ fontWeight: 600 }}>{value}</div>
    </div>
  )
}

function LogRow({
  log,
  previews,
  selected,
  expanded,
  onToggleSelect,
  onToggleExpand,
}: {
  log: RetrievalLogOut
  previews: Record<string, ChunkPreview>
  selected: boolean
  expanded: boolean
  onToggleSelect: () => void
  onToggleExpand: () => void
}) {
  const ratingsMap = Object.fromEntries(log.ratings.map((r) => [r.chunk_id, r.rating]))
  const isRated = log.ratings.length > 0
  const isFullyRated =
    !!log.final_chunk_ids && log.final_chunk_ids.every((id) => id in ratingsMap)

  return (
    <div
      style={{
        border: "1px solid #eee",
        borderRadius: 8,
        background: "#fff",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "10px 12px",
          cursor: "pointer",
        }}
        onClick={onToggleExpand}
      >
        <input
          type="checkbox"
          checked={selected}
          onClick={(e) => e.stopPropagation()}
          onChange={onToggleSelect}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 13,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {log.query}
          </div>
          <div style={{ fontSize: 11, color: "#999", marginTop: 2 }}>
            {log.chunking_strategy ?? "—"} · rerank {log.rerank_enabled ? "on" : "off"} ·{" "}
            {new Date(log.created_at).toLocaleString()}
            {log.is_replay && (
              <span
                style={{
                  marginLeft: 6,
                  fontSize: 10,
                  fontWeight: 600,
                  color: "#7c3aed",
                  background: "#f3e8ff",
                  borderRadius: 999,
                  padding: "1px 6px",
                }}
              >
                REPLAY
              </span>
            )}
          </div>
        </div>
        <span
          style={{
            fontSize: 11,
            fontWeight: 500,
            color: isFullyRated ? "#16a34a" : isRated ? "#b45309" : "#999",
          }}
        >
          {isFullyRated ? "Fully rated" : isRated ? "Partially rated" : "Unrated"}
        </span>
        <span style={{ fontSize: 12, color: "#bbb" }}>{expanded ? "▲" : "▼"}</span>
      </div>

      {expanded && (
        <div
          style={{
            padding: "12px",
            borderTop: "1px solid #eee",
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 16,
          }}
        >
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#666", marginBottom: 6 }}>
              Stage 1 (bi-encoder retrieval order)
            </div>
            <ChunkList chunkIds={log.stage1_chunk_ids} ratings={ratingsMap} previews={previews} />
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#666", marginBottom: 6 }}>
              {log.rerank_enabled ? "Stage 2 (cross-encoder re-ranked order)" : "Final (rerank off)"}
            </div>
            <ChunkList
              chunkIds={log.rerank_enabled ? log.stage2_chunk_ids : log.final_chunk_ids}
              ratings={ratingsMap}
              previews={previews}
            />
          </div>
        </div>
      )}
    </div>
  )
}
