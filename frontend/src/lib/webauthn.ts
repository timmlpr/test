// WebAuthn (passkeys) helpers: JSON options from py_webauthn ⇄ browser credential API (base64url encoding).
const toBuf = (s: string) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
const toB64u = (b: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

export const passkeysSupported = () => typeof window !== "undefined" && !!window.PublicKeyCredential;

export async function createPasskey(opts: any) {
  const pk: PublicKeyCredentialCreationOptions = {
    ...opts, challenge: toBuf(opts.challenge), user: { ...opts.user, id: toBuf(opts.user.id) },
    excludeCredentials: (opts.excludeCredentials || []).map((c: any) => ({ ...c, id: toBuf(c.id) })),
  };
  const cred = (await navigator.credentials.create({ publicKey: pk })) as PublicKeyCredential;
  const r = cred.response as AuthenticatorAttestationResponse;
  return { id: cred.id, rawId: toB64u(cred.rawId), type: cred.type, response: { clientDataJSON: toB64u(r.clientDataJSON), attestationObject: toB64u(r.attestationObject),
    transports: r.getTransports?.() ?? [] }, clientExtensionResults: cred.getClientExtensionResults() };
}

export async function getPasskey(opts: any) {
  const pk: PublicKeyCredentialRequestOptions = { ...opts, challenge: toBuf(opts.challenge), allowCredentials: (opts.allowCredentials || []).map((c: any) => ({ ...c, id: toBuf(c.id) })) };
  const cred = (await navigator.credentials.get({ publicKey: pk })) as PublicKeyCredential;
  const r = cred.response as AuthenticatorAssertionResponse;
  return { id: cred.id, rawId: toB64u(cred.rawId), type: cred.type, response: { clientDataJSON: toB64u(r.clientDataJSON), authenticatorData: toB64u(r.authenticatorData),
    signature: toB64u(r.signature), userHandle: r.userHandle ? toB64u(r.userHandle) : null }, clientExtensionResults: cred.getClientExtensionResults() };
}
