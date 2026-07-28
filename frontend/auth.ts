/**
 * NextAuth configuration for Google authentication.
 *
 * This file sets up the NextAuth authentication flow with Google as the provider.
 * It handles JWT token creation and session management, ensuring secure user authentication.
 */

import NextAuth from "next-auth"
import Google from "next-auth/providers/google"

export const { handlers, signIn, signOut, auth } = NextAuth({
    providers: [
      Google({
        clientId: process.env.GOOGLE_CLIENT_ID!,
        clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      }),
    ],
    session: { strategy: "jwt" },
    callbacks: {
      async jwt({ token, account, profile }) {
        if (account && profile) {
          token.email = profile.email
          token.name = profile.name
          token.picture = (profile as any).picture
        }
        return token
      },
      async session({ session, token }) {
        (session as any).accessToken = token
        return session
      },
    },
  })
