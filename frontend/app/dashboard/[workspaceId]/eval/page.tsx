import { auth } from "@/auth"
import { redirect } from "next/navigation"
import { getEvalMetrics, getEvalLogs } from "@/app/dashboard/actions"
import EvalDashboard from "@/components/EvalDashboard"

export default async function EvalPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>
}) {
  const session = await auth()
  if (!session) redirect("/sign-in")

  const { workspaceId } = await params

  const [metrics, logs] = await Promise.all([
    getEvalMetrics(workspaceId).catch(() => ({ configs: [], overall_coverage: 0 })),
    getEvalLogs(workspaceId, { page: 1, page_size: 20 }).catch(() => ({
      logs: [],
      total: 0,
      page: 1,
      page_size: 20,
      chunk_previews: {},
    })),
  ])

  return (
    <EvalDashboard
      workspaceId={workspaceId}
      initialMetrics={metrics}
      initialLogs={logs}
    />
  )
}
