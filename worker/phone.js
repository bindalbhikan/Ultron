// Independent D1 rows preserve overlapping jobs and their result parts.
export async function phoneJobs(request, env, action) {
  const db = env.AGENT_DB;
  const q = new URL(request.url).searchParams;
  const json = Response.json;
  const now = Date.now();
  const id = q.get("job") || "";
  // Preserve a job already running on a phone during the KV-to-D1 deployment.
  if (action !== "job") {
    const old = await env.DASH?.get("phone_job", "json");
    if (old && old.created > now - 86400000) {
      const copied = await db.prepare("INSERT OR IGNORE INTO phone_job(id,kind,items,created,taken,done,expires) VALUES(?,?,?,?,?,?,?) RETURNING id")
        .bind(old.id, old.kind, JSON.stringify(old.items), old.created, old.taken || 0, old.done || 0, old.created + 86400000).first();
      if (copied && old.done) {
        for (let part = 0; part < old.done; part++) {
          const payload = await env.DASH.get(`phone_result:${old.id}:${part}`);
          if (payload !== null) await db.prepare("INSERT OR IGNORE INTO phone_result(job_id,part,payload) VALUES(?,?,?)").bind(old.id, part, payload).run();
        }
      }
    }
  }
  if (action === "job") {
    const job = await request.json().catch(() => null);
    if (!job || !/^[a-zA-Z0-9_-]{1,100}$/.test(job.id) || job.kind !== "myntra_style" ||
        !Array.isArray(job.items) || !job.items.length || job.items.length > 100000 ||
        !job.items.every((n) => Number.isSafeInteger(n) && n > 0)) return new Response("bad job", { status: 400 });
    await db.prepare("DELETE FROM phone_result WHERE job_id IN (SELECT id FROM phone_job WHERE expires<=?)").bind(now).run();
    await db.prepare("DELETE FROM phone_job WHERE expires<=?").bind(now).run();
    const queued = await db.prepare("INSERT OR IGNORE INTO phone_job(id,kind,items,created,expires) VALUES(?,?,?,?,?) RETURNING id")
      .bind(job.id, job.kind, JSON.stringify(job.items), now, now + 86400000).first();
    return queued ? json({ queued: job.id }) : new Response("job already exists", { status: 409 });
  }
  if (action === "next") {
    // One atomic claim across phones. A phone that dies releases its job after 30 minutes.
    const job = await db.prepare(`UPDATE phone_job SET taken=? WHERE id=(
      SELECT id FROM phone_job WHERE done=0 AND expires>? AND (taken=0 OR taken<?)
      ORDER BY created,id LIMIT 1) AND done=0 AND (taken=0 OR taken<?) RETURNING id,kind,items`)
      .bind(now, now, now - 1800000, now - 1800000).first();
    return json(job ? { id: job.id, kind: job.kind, items: JSON.parse(job.items) } : {});
  }
  const job = await db.prepare("SELECT id,taken,done FROM phone_job WHERE id=? AND expires>?").bind(id, now).first();
  if (action === "result") {
    const part = Number(q.get("part") || 0);
    if (!job) return new Response("no such job", { status: 404 });
    if (!Number.isSafeInteger(part) || part < 0 || part > 10000) return new Response("bad part", { status: 400 });
    const body = await request.text();
    // Keep each D1 value within its 2 MB limit (current phone batches are much smaller).
    if (new TextEncoder().encode(body).length > 1900000) return new Response("too large", { status: 413 });
    let parsed;
    try { parsed = JSON.parse(body); } catch { return new Response("not JSON", { status: 400 }); }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return new Response("bad results", { status: 400 });
    const statements = [db.prepare("INSERT OR IGNORE INTO phone_result(job_id,part,payload) VALUES(?,?,?)").bind(id, part, body)];
    if (q.get("last") === "1") statements.push(db.prepare("UPDATE phone_job SET done=? WHERE id=? AND done=0").bind(part + 1, id));
    await db.batch(statements);
    return json({ stored: part });
  }
  if (action === "collect") {
    if (!job) return json({ done: 0, missing: true });
    if (!job.done) return json({ done: 0, taken: job.taken });
    let { results: parts } = await db.prepare("SELECT part,payload FROM phone_result WHERE job_id=? AND part<? ORDER BY part").bind(id, job.done).all();
    if (parts.length !== job.done && env.DASH) {
      const present = new Set(parts.map((p) => p.part));
      for (let i = 0; i < job.done; i++) {
        if (present.has(i)) continue;
        const payload = await env.DASH.get(`phone_result:${id}:${i}`);
        if (payload !== null) await db.prepare("INSERT OR IGNORE INTO phone_result(job_id,part,payload) VALUES(?,?,?)").bind(id, i, payload).run();
      }
      ({ results: parts } = await db.prepare("SELECT part,payload FROM phone_result WHERE job_id=? AND part<? ORDER BY part").bind(id, job.done).all());
    }
    if (parts.length !== job.done || parts.some((p, i) => p.part !== i)) return json({ done: 0, taken: job.taken });
    const results = Object.assign({}, ...parts.map((p) => JSON.parse(p.payload)));
    return json({ done: job.done, taken: job.taken, results });
  }
  return new Response("unknown", { status: 404 });
}
