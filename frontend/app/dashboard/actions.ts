"use server"

import {
  api,
  type Document,
  type Workspace,
  type MetricsResponse,
  type RetrievalLogsResponse,
  type ReplayResponse,
} from "@/lib/api"

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

export async function listDocuments(workspaceId: string): Promise<Document[]> {
  return api.documents.list(workspaceId)
}

export async function uploadDocument(
  workspaceId: string,
  formData: FormData
): Promise<Document> {
  const file = formData.get("file")
  if (!(file instanceof File)) throw new Error("No file provided")
  return api.documents.upload(workspaceId, file)
}

export async function deleteDocument(
  workspaceId: string,
  documentId: string
): Promise<void> {
  return api.documents.delete(workspaceId, documentId)
}

export async function rechunkDocument(
  workspaceId: string,
  documentId: string,
  strategy: string
): Promise<{ status: string }> {
  return api.documents.rechunk(workspaceId, documentId, strategy)
}

export async function getEvalMetrics(workspaceId: string): Promise<MetricsResponse> {
  return api.eval.metrics(workspaceId)
}

export async function getEvalLogs(
  workspaceId: string,
  params: {
    page?: number
    page_size?: number
    chunking_strategy?: string
    rerank?: boolean
  } = {}
): Promise<RetrievalLogsResponse> {
  return api.eval.logs(workspaceId, params)
}

export async function replayEvalQueries(
  workspaceId: string,
  logIds: string[],
  chunkingStrategy: string,
  rerankEnabled: boolean
): Promise<ReplayResponse> {
  return api.eval.replay(workspaceId, logIds, chunkingStrategy, rerankEnabled)
}
