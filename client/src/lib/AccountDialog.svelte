<script lang="ts">
  import { X } from "@lucide/svelte";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Label } from "$lib/components/ui/label";
  import { signIn } from "./account.svelte";

  let dialog: HTMLDialogElement;
  let making = $state(false);
  let name = $state(""), email = $state(""), password = $state("");
  let busy = $state(false), error = $state("");
  let afterSignIn: (() => void) | undefined;

  /** Opens the sign-in form. `then` runs after signing in. */
  export function show(then?: () => void) {
    error = "";
    afterSignIn = then;
    dialog.showModal();
  }

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    error = "";
    try {
      await signIn(email.trim(), password, making ? name.trim() : undefined);
      password = "";
      dialog.close();
      afterSignIn?.();
      afterSignIn = undefined;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }
</script>

<dialog bind:this={dialog} aria-labelledby="account-title"
  class="m-auto w-[min(34rem,calc(100vw-2rem))] rounded-[2rem] bg-card p-6 text-foreground shadow-xl backdrop:bg-ink-950/40 print:hidden">
  <div class="flex items-start justify-between gap-4">
    <h2 id="account-title" class="display text-4xl">{making ? "Make an account" : "Sign in"}</h2>
    <Button variant="ghost" size="icon-sm" class="rounded-full" aria-label="Close" onclick={() => dialog.close()}><X aria-hidden="true" /></Button>
  </div>

  <p class="mt-2 text-muted-foreground">Save your designs and download them again any time.</p>
  <form class="mt-5 space-y-4" onsubmit={submit}>
    {#if making}
      <div class="space-y-1.5"><Label for="account-name">Your name</Label><Input id="account-name" bind:value={name} autocomplete="name" required /></div>
    {/if}
    <div class="space-y-1.5"><Label for="account-email">Email</Label><Input id="account-email" type="email" bind:value={email} autocomplete="email" required /></div>
    <div class="space-y-1.5">
      <Label for="account-password">Password</Label>
      <Input id="account-password" type="password" bind:value={password} minlength={8} required
        autocomplete={making ? "new-password" : "current-password"} />
      {#if making}<p class="text-sm text-muted-foreground">At least 8 characters.</p>{/if}
    </div>
    <Button type="submit" class="w-full" disabled={busy}>{busy ? "One moment…" : making ? "Make my account" : "Sign in"}</Button>
  </form>
  <p class="mt-4 text-center text-muted-foreground">
    {making ? "Already have an account?" : "New here?"}
    <button type="button" class="font-semibold text-foreground underline underline-offset-4" onclick={() => { making = !making; error = ""; }}>
      {making ? "Sign in" : "Make an account"}
    </button>
  </p>

  {#if error}<p role="alert" class="mt-4 rounded-2xl bg-ink-950 px-4 py-3 text-white">{error}</p>{/if}
</dialog>
