import { auth } from "@/auth"
import { redirect } from "next/navigation"
import { api } from "@/lib/api"
import DocumentsPanel from "@/components/DocumentsPanel"

export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ workspaceId: string }>
}) {
  const session = await auth()
  if (!session) redirect("/sign-in")

  const { workspaceId } = await params
  const documents = await api.documents.list(workspaceId)

  return (
    <DocumentsPanel
      workspaceId={workspaceId}
      initialDocuments={documents}
    />
  )
}