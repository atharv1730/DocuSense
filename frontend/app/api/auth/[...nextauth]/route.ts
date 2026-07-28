/**
 * NextAuth route handler for authentication endpoints.
 *
 * This file exports the GET and POST handlers for the NextAuth authentication routes.
 * It uses the handlers from the auth.ts file to handle the authentication flow.
 */
import { handlers } from "@/auth"
export const { GET, POST } = handlers