/**
 * Dashboard page for the application.
 *
 * This page displays the dashboard for the application.
 * It requires authentication and displays the list of workspaces for the user.
 */

import { auth } from "@/auth"
import { redirect } from "next/navigation"
import { api } from "@/lib/api"
import WorkspaceDashboard from "@/components/WorkspaceDashboard"

export default async function DashboardPage() {
  const session = await auth()
  if (!session) redirect("/sign-in")

  const workspaces = await api.workspaces.list()

  return <WorkspaceDashboard initialWorkspaces={workspaces} />
}