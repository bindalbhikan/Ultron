import { betterAuth } from 'better-auth';
import { bearer } from 'better-auth/plugins';
import { drizzleAdapter } from '@better-auth/drizzle-adapter';
import { drizzle } from 'drizzle-orm/d1';
import * as schema from './schema';

export interface Env {
  DB: D1Database;
  AUTH_SECRET: string;
  AUTH_BASE_URL: string;
  APP_ORIGIN: string;
}

export function createAuth(env: Env) {
  return betterAuth({
    appName: 'Ultron', secret: env.AUTH_SECRET, baseURL: env.AUTH_BASE_URL, basePath: '/api/auth',
    database: drizzleAdapter(drizzle(env.DB), { provider: 'sqlite', schema, transaction: false }),
    trustedOrigins: env.APP_ORIGIN.split(',').map((origin) => origin.trim()),
    emailAndPassword: { enabled: true, minPasswordLength: 12, maxPasswordLength: 128, autoSignIn: false },
    session: { expiresIn: 60 * 60 * 12, updateAge: 60 * 60, cookieCache: { enabled: false } },
    rateLimit: { enabled: true, storage: 'database', window: 60, max: 60,
      customRules: { '/sign-in/email': { window: 60, max: 5 }, '/sign-up/email': { window: 3600, max: 5 } } },
    advanced: { ipAddress: { ipAddressHeaders: ['cf-connecting-ip'] } },
    logger: { disabled: true },
    plugins: [bearer()],
  });
}
