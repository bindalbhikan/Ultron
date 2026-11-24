import type { Env } from './auth';

const files: Record<string, string> = { android: 'ULTRON.apk', windows: 'ULTRON-Windows.zip', macos: 'ULTRON-macOS.zip', linux: 'ULTRON-Linux.tar.gz' };
const keyPattern = /^releases\/[1-9][0-9]{0,9}\/(android|windows|macos|linux)\/[a-f0-9]{64}\/ULTRON[\w.-]*$/;
const fail = (error: string, status = 400) => Response.json({ error }, { status });

// Release bytes are streamed to R2 in 10 MB parts; the manifest is published only after completion.
export async function releases(request: Request, env: Env): Promise<Response | null> {
  const url = new URL(request.url);
  const path = url.pathname;
  if (!path.startsWith('/api/releases/')) return null;
  if (!env.RELEASES) return fail('App update storage is not enabled yet.', 503);
  const bucket = env.RELEASES;
  if (path === '/api/releases/latest' && request.method === 'GET') {
    const platform = url.searchParams.get('platform') || '';
    if (!Object.hasOwn(files, platform)) return fail('Unknown platform.');
    const release = await env.DB.prepare('SELECT version,build,sha256,size,object_key AS objectKey,published FROM app_release WHERE platform=?').bind(platform).first();
    if (!release) return fail('No update has been published for this platform yet.', 404);
    return Response.json({ ...release, url: new URL('/api/releases/files/' + release.objectKey, url.origin).href });
  }
  if (path.startsWith('/api/releases/files/') && ['GET', 'HEAD'].includes(request.method)) {
    const key = path.slice('/api/releases/files/'.length);
    if (!keyPattern.test(key)) return fail('Unknown release.', 404);
    const object = request.method === 'HEAD' ? await bucket.head(key) : await bucket.get(key, { range: request.headers });
    if (!object) return fail('Release file is unavailable.', 404);
    const headers = new Headers({ 'Content-Type': 'application/octet-stream', 'Accept-Ranges': 'bytes',
      'Content-Disposition': 'attachment; filename="' + key.split('/').pop() + '"', ETag: object.httpEtag });
    const range = 'range' in object ? object.range : undefined;
    const offset = range && 'offset' in range ? range.offset ?? 0 : 0;
    const length = range && 'length' in range ? range.length ?? object.size : object.size;
    headers.set('Content-Length', String(length));
    if (range) headers.set('Content-Range', `bytes ${offset}-${offset + length - 1}/${object.size}`);
    return new Response('body' in object ? object.body as ReadableStream : null, { status: range ? 206 : 200, headers });
  }
  // This credential is already used by the private CI runner to reach the operations service.
  if (!env.WORKER_TOKEN || request.headers.get('Authorization') !== 'Bearer ' + env.WORKER_TOKEN) return fail('Forbidden.', 403);
  if (path === '/api/releases/upload' && request.method === 'POST') {
    const data = await request.json() as Record<string, unknown>;
    const { platform, version, sha256, size, build } = data;
    if (typeof platform !== 'string' || !Object.hasOwn(files, platform) || typeof version !== 'string' || !/^\d+\.\d+\.\d+$/.test(version) ||
        typeof sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(sha256) || !Number.isSafeInteger(build) || Number(build) < 1 ||
        Number(build) > 2147483647 || !Number.isSafeInteger(size) || Number(size) < 1 || Number(size) > 2000000000) return fail('Invalid release.');
    const key = `releases/${build}/${platform}/${sha256}/${files[platform]}`;
    const upload = await bucket.createMultipartUpload(key, { customMetadata: { platform, version, sha256, size: String(size), build: String(build) } });
    return Response.json({ key, uploadId: upload.uploadId });
  }
  const key = url.searchParams.get('key') || '';
  const uploadId = url.searchParams.get('uploadId') || '';
  if (!keyPattern.test(key) || !uploadId || uploadId.length > 1000) return fail('Invalid upload.');
  const upload = bucket.resumeMultipartUpload(key, uploadId);
  if (path === '/api/releases/upload' && request.method === 'PUT') {
    const part = Number(url.searchParams.get('part'));
    const length = Number(request.headers.get('Content-Length'));
    if (!Number.isInteger(part) || part < 1 || part > 10000 || !length || length > 10000000 || !request.body) return fail('Invalid upload part.');
    return Response.json(await upload.uploadPart(part, request.body));
  }
  if (path === '/api/releases/complete' && request.method === 'POST') {
    const { parts } = await request.json() as { parts: R2UploadedPart[] };
    if (!Array.isArray(parts) || !parts.length || parts.length > 10000 ||
        parts.some((p, i) => p.partNumber !== i + 1 || typeof p.etag !== 'string')) return fail('Invalid upload parts.');
    const object = await upload.complete(parts);
    const meta = object.customMetadata!;
    if (object.size !== Number(meta.size)) return fail('Release size does not match; not published.');
    await env.DB.prepare(`INSERT INTO app_release(platform,version,build,sha256,size,object_key,published) VALUES(?,?,?,?,?,?,?)
      ON CONFLICT(platform) DO UPDATE SET version=excluded.version,build=excluded.build,sha256=excluded.sha256,
      size=excluded.size,object_key=excluded.object_key,published=excluded.published WHERE excluded.build>app_release.build`)
      .bind(meta.platform, meta.version, Number(meta.build), meta.sha256, object.size, key, Date.now()).run();
    return Response.json({ published: meta.platform, build: Number(meta.build) });
  }
  return fail('Unknown release route.', 404);
}
