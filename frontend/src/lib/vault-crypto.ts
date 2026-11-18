// End-to-end encryption for the digital estate (M-14): PBKDF2 (SHA-256, 310k iterations) → AES-GCM 256.
// The passphrase and plaintext never leave the browser; the server only stores ciphertext, salt and iv.
const b64 = (b: ArrayBuffer | Uint8Array) => btoa(String.fromCharCode(...new Uint8Array(b instanceof Uint8Array ? b : new Uint8Array(b))));
const unb64 = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

async function key(pass: string, salt: Uint8Array) {
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(pass), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey({ name: "PBKDF2", salt: salt as BufferSource, iterations: 310_000, hash: "SHA-256" }, base, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
}

export async function encryptVault(plain: string, pass: string) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await key(pass, salt), new TextEncoder().encode(plain));
  return { ciphertext: b64(ct), salt: b64(salt), iv: b64(iv) };
}

export async function decryptVault(v: { ciphertext: string; salt: string; iv: string }, pass: string) {
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(v.iv) as BufferSource }, await key(pass, unb64(v.salt)), unb64(v.ciphertext) as BufferSource);
  return new TextDecoder().decode(pt);
}
