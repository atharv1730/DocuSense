/**
 * Sign in page for the application.
 *
 * This page allows users to sign in with Google to access the application.
 */

import { signIn } from "@/auth"

export default function SignInPage() {
  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
    }}>
      <div style={{ textAlign: "center", maxWidth: 360 }}>
        <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 8 }}>DocuSense</h1>
        <p style={{ color: "#666", marginBottom: 32, fontSize: 14 }}>
          AI-powered document intelligence
        </p>
        <form action={async () => {
          "use server"
          await signIn("google", { redirectTo: "/dashboard" })
        }}>
          <button type="submit" style={{
            width: "100%",
            padding: "10px 16px",
            border: "1px solid #ddd",
            borderRadius: 8,
            background: "#fff",
            cursor: "pointer",
            fontSize: 14,
            fontWeight: 500,
          }}>
            Sign in with Google
          </button>
        </form>
      </div>
    </div>
  )
}