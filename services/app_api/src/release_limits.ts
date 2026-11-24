// Deliberately below R2 Standard's account-wide free allowances. No paid fallback.
export const RELEASE_LIMITS = Object.freeze({
  storageBytes: 2_000_000_000,
  maxFileBytes: 250_000_000,
  partBytes: 10_000_000,
  classA: 10_000,
  classB: 100_000,
});

export class ReleaseLimitError extends Error {}

// Count before touching R2; concurrent requests cannot race past the limit.
// Failed R2 requests still consume a reservation; uncertainty never creates extra allowance.
export async function chargeR2(db: D1Database, kind: 'A' | 'B') {
  const period = new Date().toISOString().slice(0, 7);
  const limit = kind === 'A' ? RELEASE_LIMITS.classA : RELEASE_LIMITS.classB;
  const allowed = await db.prepare(`INSERT INTO release_usage(period,kind,used) VALUES(?,?,1)
    ON CONFLICT(period,kind) DO UPDATE SET used=release_usage.used+1 WHERE release_usage.used<?
    RETURNING used`).bind(period, kind, limit).first();
  if (!allowed) throw new ReleaseLimitError('The free update request budget is reached. Updates are paused until next month.');
}

export async function reserveStorage(db: D1Database, objectKey: string, size: number) {
  const id = crypto.randomUUID();
  const reserved = await db.prepare(`INSERT INTO release_upload(id,object_key,size,created)
    SELECT ?,?,?,? WHERE (SELECT COALESCE(SUM(size),0) FROM release_upload)+?<=?
    RETURNING id`).bind(id, objectKey, size, Date.now(), size, RELEASE_LIMITS.storageBytes).first();
  if (!reserved) throw new ReleaseLimitError('The free update storage budget is reached. Uploads are paused; existing updates remain available.');
  return id;
}
