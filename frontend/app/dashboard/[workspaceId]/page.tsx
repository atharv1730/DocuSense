import { auth } from "@/auth"
import { redirect } from "next/navigation"
import { api } from "@/lib/api"
import DocumentsPanel from "@/components/DocumentsPanel"

export default async function WorkspacePage({
  params,
}: {
  params: { workspaceId: string }
}) {
  const session = await auth()
  if (!session) redirect("/sign-in")

  const documents = await api.documents.list(params.workspaceId)

  return (
    <DocumentsPanel
      workspaceId={params.workspaceId}
      initialDocuments={documents}
    />
  )
}