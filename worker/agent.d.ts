/** Shared JavaScript worker entry point consumed by the app API integration checks. */
export function makeAgent(options: { repo: string; [key: string]: unknown }): {
  route(request: Request, env: Record<string, unknown>, path: string): Response | Promise<Response> | null;
};
