import { auth } from "@/auth"
import { redirect } from "next/navigation"
import { api } from "@/lib/api"
import CompareView from "@/components/CompareView"

export default async function ComparePage({
  params,
}: {
  params: Promise<{ workspaceId: string }>
}) {
  const session = await auth()
  if (!session) redirect("/sign-in")

  const { workspaceId } = await params
  const documents = await api.documents.list(workspaceId).catch(() => [])

  return <CompareView workspaceId={workspaceId} initialDocuments={documents} />
}
