/**
 * Simple, production-ready authorization utilities for Vercel API routes.
 */

export function validateApiKey(request: Request): { authorized: boolean; error?: string } {
  const serverSecret = process.env.APP_ACCESS_TOKEN || process.env.CRON_SECRET;
  // If no server-side secret is configured, allow public access
  if (!serverSecret) {
    return { authorized: true };
  }

  const authHeader = request.headers.get("authorization");
  if (!authHeader) {
    return { authorized: false, error: "Missing Authorization header" };
  }

  const token = authHeader.replace(/^Bearer\s+/i, "").trim();
  if (token !== serverSecret) {
    return { authorized: false, error: "Invalid access token" };
  }

  return { authorized: true };
}
