import { auth } from "@/auth"
import { redirect } from "next/navigation"
import { getAuthToken, api } from "@/lib/api"
import ChatPanel from "@/components/ChatPanel"

export default async function ChatPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>
}) {
  const session = await auth()
  if (!session) redirect("/sign-in")

  const { workspaceId } = await params
  const authToken = await getAuthToken()
  if (!authToken) redirect("/sign-in")

  const documents = await api.documents.list(workspaceId).catch(() => [])
  const conversations = await api.conversations.list(workspaceId).catch(() => [])

  return (
    <ChatPanel
      workspaceId={workspaceId}
      authToken={authToken}
      initialDocuments={documents}
      initialConversations={conversations}
    />
  )
}
