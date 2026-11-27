import { createAuthClient } from "@neon/auth";
import { BetterAuthVanillaAdapter } from "@neon/auth/vanilla";

// The adapter is named so the types narrow to the plain Better Auth client
const create = (url: string) => createAuthClient(url, { adapter: BetterAuthVanillaAdapter() });
let client: ReturnType<typeof create> | undefined;
/** Neon Auth, reached through this site's /api/auth so its cookies are first-party (Safari blocks them otherwise). */
const auth = () => (client ??= create(new URL("/api/auth", window.location.href).href));

/** Who is signed in. `ready` turns true once the first check has come back. */
export const account = $state<{ user: { name: string; email: string } | null; ready: boolean }>({ user: null, ready: false });

export async function refreshAccount() {
  const { data } = await auth().getSession();
  account.user = data?.user ? { name: data.user.name, email: data.user.email } : null;
  account.ready = true;
}

/** A fresh token for the server (they last 15 minutes; getSession renews it). */
export async function accountToken(): Promise<string> {
  const { data } = await auth().getSession();
  if (!data?.session.token) {
    account.user = null;
    throw new Error("Please sign in again.");
  }
  return data.session.token;
}

/** Signs in, or makes an account when `name` is given. Throws an Error with a readable message. */
export async function signIn(email: string, password: string, name?: string) {
  const { error } = name ? await auth().signUp.email({ email, password, name }) : await auth().signIn.email({ email, password });
  // Our server answers 503 when sign-in isn't configured; the library would only say "HTTP 503"
  if (error?.status === 503) throw new Error("Signing in isn’t set up on this server yet.");
  if (error) throw new Error(error.message || "That didn’t work. Please check your details and try again.");
  await refreshAccount();
}

export async function signOut() {
  await auth().signOut();
  account.user = null;
}
