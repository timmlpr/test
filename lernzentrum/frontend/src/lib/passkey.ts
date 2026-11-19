// WebAuthn helpers (Face ID / Touch ID passkeys) – JSON <-> ArrayBuffer conversion for the py_webauthn backend.
import { api } from "./api";
import type { User } from "./types";

const b64urlToBuf = (s: string) => {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const bin = atob((s + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0)).buffer;
};
const bufToB64url = (b: ArrayBuffer) =>
  btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

type Json = Record<string, unknown>;

export function passkeySupported(): boolean {
  return typeof window !== "undefined" && !!window.PublicKeyCredential;
}

export async function registerPasskey(): Promise<void> {
  const o = await api.post<Json>("/auth/passkey/register/options");
  const pub = {
    ...o,
    challenge: b64urlToBuf(o.challenge as string),
    user: { ...(o.user as Json), id: b64urlToBuf((o.user as Json).id as string) },
    excludeCredentials: ((o.excludeCredentials as Json[]) || []).map((c) => ({ ...c, id: b64urlToBuf(c.id as string) })),
  } as unknown as PublicKeyCredentialCreationOptions;
  const cred = (await navigator.credentials.create({ publicKey: pub })) as PublicKeyCredential;
  const r = cred.response as AuthenticatorAttestationResponse;
  await api.post("/auth/passkey/register/verify", {
    id: cred.id,
    rawId: bufToB64url(cred.rawId),
    type: cred.type,
    response: { clientDataJSON: bufToB64url(r.clientDataJSON), attestationObject: bufToB64url(r.attestationObject) },
    label: "Face ID / Touch ID",
  });
}

export async function passkeyLogin(email: string): Promise<User> {
  const o = await api.post<Json>("/auth/passkey/login/options", { email });
  const pub = {
    ...o,
    challenge: b64urlToBuf(o.challenge as string),
    allowCredentials: ((o.allowCredentials as Json[]) || []).map((c) => ({ ...c, id: b64urlToBuf(c.id as string) })),
  } as unknown as PublicKeyCredentialRequestOptions;
  const cred = (await navigator.credentials.get({ publicKey: pub })) as PublicKeyCredential;
  const r = cred.response as AuthenticatorAssertionResponse;
  return api.post<User>("/auth/passkey/login/verify", {
    id: cred.id,
    rawId: bufToB64url(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: bufToB64url(r.clientDataJSON),
      authenticatorData: bufToB64url(r.authenticatorData),
      signature: bufToB64url(r.signature),
      userHandle: r.userHandle ? bufToB64url(r.userHandle) : null,
    },
  });
}
