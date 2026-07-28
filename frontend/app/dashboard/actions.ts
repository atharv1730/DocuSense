"use server"

import { api, type Workspace } from "@/lib/api"

export async function createWorkspace(name: string): Promise<Workspace> {
  return api.workspaces.create(name)
}

export async function renameWorkspace(
  id: string,
  name: string
): Promise<Workspace> {
  return api.workspaces.rename(id, name)
}

export async function deleteWorkspace(id: string): Promise<void> {
  return api.workspaces.delete(id)
}
