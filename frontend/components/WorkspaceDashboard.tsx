"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import type { Workspace } from "@/lib/api"
import {
  createWorkspace,
  renameWorkspace,
  deleteWorkspace,
} from "@/app/dashboard/actions"

export default function WorkspaceDashboard({
  initialWorkspaces,
}: {
  initialWorkspaces: Workspace[]
}) {
  const router = useRouter()
  const [workspaces, setWorkspaces] = useState(initialWorkspaces)
  const [newName, setNewName] = useState("")
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState("")

  async function handleCreate() {
    if (!newName.trim()) return
    const ws = await createWorkspace(newName.trim())
    setWorkspaces((prev) => [ws, ...prev])
    setNewName("")
  }

  async function handleRename(id: string) {
    if (!editName.trim()) return
    const updated = await renameWorkspace(id, editName.trim())
    setWorkspaces((prev) => prev.map((w) => (w.id === id ? updated : w)))
    setEditingId(null)
  }

  async function handleDelete(id: string) {
    await deleteWorkspace(id)
    setWorkspaces((prev) => prev.filter((w) => w.id !== id))
  }

  return (
    <div style={{ maxWidth: 600, margin: "60px auto", padding: "0 16px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>Your workspaces</h1>

      <div style={{ display: "flex", gap: 8, marginBottom: 32 }}>
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          placeholder="New workspace name"
          style={{ flex: 1, padding: "8px 12px", border: "1px solid #ddd", borderRadius: 6, fontSize: 14 }}
        />
        <button
          onClick={handleCreate}
          style={{ padding: "8px 16px", background: "#111", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 14 }}
        >
          Create
        </button>
      </div>

      {workspaces.length === 0 && (
        <p style={{ color: "#999", fontSize: 14 }}>No workspaces yet. Create one above.</p>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {workspaces.map((ws) => (
          <div key={ws.id} style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "12px 16px", border: "1px solid #eee",
            borderRadius: 8, background: "#fff",
          }}>
            {editingId === ws.id ? (
              <>
                <input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleRename(ws.id)}
                  autoFocus
                  style={{ flex: 1, padding: "4px 8px", border: "1px solid #ddd", borderRadius: 4, fontSize: 14 }}
                />
                <button onClick={() => handleRename(ws.id)} style={{ fontSize: 13, cursor: "pointer" }}>Save</button>
                <button onClick={() => setEditingId(null)} style={{ fontSize: 13, cursor: "pointer" }}>Cancel</button>
              </>
            ) : (
              <>
                <span
                  style={{ flex: 1, fontSize: 15, cursor: "pointer" }}
                  onClick={() => router.push(`/dashboard/${ws.id}`)}
                >
                  {ws.name}
                </span>
                <button onClick={() => { setEditingId(ws.id); setEditName(ws.name) }} style={{ fontSize: 13, color: "#666", cursor: "pointer", background: "none", border: "none" }}>Rename</button>
                <button onClick={() => handleDelete(ws.id)} style={{ fontSize: 13, color: "#c00", cursor: "pointer", background: "none", border: "none" }}>Delete</button>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}