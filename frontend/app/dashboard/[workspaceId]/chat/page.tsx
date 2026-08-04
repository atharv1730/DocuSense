import { auth } from "@/auth"
import { redirect } from "next/navigation"
import { getAuthToken } from "@/lib/api"
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

  return <ChatPanel workspaceId={workspaceId} authToken={authToken} />
}
