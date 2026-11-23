import { betterAuth } from 'better-auth';
import { bearer, username } from 'better-auth/plugins';
import { drizzleAdapter } from '@better-auth/drizzle-adapter';
import { drizzle } from 'drizzle-orm/d1';
import * as schema from './schema';

export interface Env {
  DB: D1Database;
  AUTH_SECRET: string;
  // SHA-256 (hex) of the one-time setup code that makes the first administrator (POST /api/setup)
  SETUP_CODE_HASH?: string;
  // encrypts the agent's model API keys at rest (src/keys.ts); the Telegram worker holds the same secret
  KEYS_SECRET?: string;
  // the Telegram worker (workflows, runs, approvals, reports, connections): its URL and its DASHBOARD_TOKEN
  WORKER_URL?: string;
  WORKER_TOKEN?: string;
  AUTH_BASE_URL: string;
  APP_ORIGIN: string;
}

export function createAuth(env: Env) {
  return betterAuth({
    appName: 'Ultron', secret: env.AUTH_SECRET, baseURL: env.AUTH_BASE_URL, basePath: '/api/auth',
    database: drizzleAdapter(drizzle(env.DB), { provider: 'sqlite', schema, transaction: false }),
    trustedOrigins: env.APP_ORIGIN.split(',').map((origin) => origin.trim()),
    emailAndPassword: { enabled: true, minPasswordLength: 8, maxPasswordLength: 128, autoSignIn: false },
    session: { expiresIn: 60 * 60 * 12, updateAge: 60 * 60, cookieCache: { enabled: false } },
    rateLimit: { enabled: true, storage: 'database', window: 60, max: 60,
      customRules: { '/sign-in/email': { window: 60, max: 5 }, '/sign-in/username': { window: 60, max: 5 },
        '/sign-up/email': { window: 3600, max: 5 } } },
    advanced: { ipAddress: { ipAddressHeaders: ['cf-connecting-ip'] } },
    logger: { disabled: true },
    // sign-in by username (lower-case, 3-30 letters, digits, dot, underscore); the typed form is kept for display
    plugins: [bearer(), username({ minUsernameLength: 3, maxUsernameLength: 30 })],
  });
}
