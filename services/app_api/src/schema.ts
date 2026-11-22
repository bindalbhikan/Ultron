import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';

const date = (name: string) => integer(name, { mode: 'timestamp_ms' });
export const user = sqliteTable('user', {
  id: text('id').primaryKey(), name: text('name').notNull(), email: text('email').notNull().unique(),
  emailVerified: integer('email_verified', { mode: 'boolean' }).notNull().default(false), image: text('image'),
  createdAt: date('created_at').notNull(), updatedAt: date('updated_at').notNull(),
  username: text('username').unique(), displayUsername: text('display_username'),
});
export const session = sqliteTable('session', {
  id: text('id').primaryKey(), expiresAt: date('expires_at').notNull(), token: text('token').notNull().unique(),
  createdAt: date('created_at').notNull(), updatedAt: date('updated_at').notNull(),
  ipAddress: text('ip_address'), userAgent: text('user_agent'),
  userId: text('user_id').notNull().references(() => user.id, { onDelete: 'cascade' }),
});
export const account = sqliteTable('account', {
  id: text('id').primaryKey(), accountId: text('account_id').notNull(), providerId: text('provider_id').notNull(),
  userId: text('user_id').notNull().references(() => user.id, { onDelete: 'cascade' }),
  accessToken: text('access_token'), refreshToken: text('refresh_token'), idToken: text('id_token'),
  accessTokenExpiresAt: date('access_token_expires_at'), refreshTokenExpiresAt: date('refresh_token_expires_at'),
  scope: text('scope'), password: text('password'), createdAt: date('created_at').notNull(), updatedAt: date('updated_at').notNull(),
});
export const verification = sqliteTable('verification', {
  id: text('id').primaryKey(), identifier: text('identifier').notNull(), value: text('value').notNull(),
  expiresAt: date('expires_at').notNull(), createdAt: date('created_at').notNull(), updatedAt: date('updated_at').notNull(),
});
export const rateLimit = sqliteTable('rate_limit', {
  id: text('id').primaryKey(), key: text('key').notNull().unique(), count: integer('count').notNull(),
  lastRequest: integer('last_request').notNull(),
});
