// The agent's model API keys, encrypted at rest: AES-GCM with a key derived (SHA-256) from KEYS_SECRET, the same
// secret the Telegram worker holds (worker/agent.js decrypts them for the Python agent). The app API only
// encrypts and lists; it never sends a key back to the app.
const b64 = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes));

async function aesKey(secret: string) {
  const raw = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(secret));
  return crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt', 'decrypt']);
}

export async function sealKey(secret: string, plain: string) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const sealed = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, await aesKey(secret), new TextEncoder().encode(plain));
  return { iv: b64(iv), ciphertext: b64(new Uint8Array(sealed)) };
}

export async function openKey(secret: string, iv: string, ciphertext: string) {
  const bytes = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: bytes(iv) }, await aesKey(secret), bytes(ciphertext));
  return new TextDecoder().decode(plain);
}
