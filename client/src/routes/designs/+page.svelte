<script lang="ts">
  import { Download, LoaderCircle, LogOut, Plus, Trash2 } from "@lucide/svelte";
  import { Button } from "$lib/components/ui/button";
  import AccountDialog from "$lib/AccountDialog.svelte";
  import { account, accountToken, signOut } from "$lib/account.svelte";
  import { deleteDesign, getDesignFile, listDesigns, saveFile, type SavedDesign } from "$lib/api";

  let accountDialog: AccountDialog;
  let designs = $state<SavedDesign[] | null>(null);
  let busy = $state(false), error = $state("");
  /** The design and button being worked on, to show a spinner there */
  let pending = $state("");

  async function attempt(work: () => Promise<unknown>, what = "") {
    busy = true;
    pending = what;
    error = "";
    try {
      await work();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
      pending = "";
    }
  }

  // Loads once someone is signed in (on arrival, or after signing in here)
  $effect(() => {
    if (account.user && !designs) attempt(async () => (designs = await listDesigns(await accountToken())));
  });

  const download = (d: SavedDesign) =>
    attempt(async () => {
      const file = await getDesignFile(await accountToken(), d.id);
      saveFile(file.file_base64, file.file_name);
    }, `${d.id}:download`);
  function remove(d: SavedDesign) {
    if (!confirm(`Delete “${d.name}”? This can’t be undone.`)) return;
    attempt(async () => {
      await deleteDesign(await accountToken(), d.id);
      designs = designs?.filter((x) => x.id !== d.id) ?? null;
    }, `${d.id}:delete`);
  }
  const leave = () => attempt(async () => { await signOut(); designs = null; }, "signout");
</script>

<svelte:head><title>My designs · Stitchery</title></svelte:head>

<div class="min-h-dvh">
  <header class="flex flex-wrap items-center gap-2 px-3 py-3 sm:gap-3 sm:px-5">
    <a href="/" class="display mr-2 text-3xl text-vermilion-500" aria-label="Stitchery home">Stitchery</a>
    {#if account.user}
      <Button variant="secondary" class="ml-auto h-10" disabled={busy} onclick={leave}>{#if pending === "signout"}<LoaderCircle aria-hidden="true" class="animate-spin" />{:else}<LogOut aria-hidden="true" />{/if} Sign out</Button>
    {/if}
    <Button href="/" class="h-10 {account.user ? '' : 'ml-auto'}"><Plus aria-hidden="true" /> New design</Button>
  </header>

  <main class="mx-3 mb-3 rounded-[2rem] bg-card p-5 sm:mx-5 sm:mb-5 sm:p-8">
    <h1 class="display text-5xl">My designs</h1>

    {#if !account.ready}
      <p class="mt-4 text-muted-foreground">One moment…</p>
    {:else if !account.user}
      <p class="mt-2 text-muted-foreground">Sign in to see the designs you’ve saved.</p>
      <Button class="mt-5" onclick={() => accountDialog.show()}>Sign in</Button>
    {:else}
      <p class="mt-2 text-muted-foreground">Signed in as {account.user.name} ({account.user.email})</p>
      {#if designs?.length}
        <ul class="mt-6 grid grid-cols-[repeat(auto-fill,minmax(14rem,1fr))] gap-4">
          {#each designs as d (d.id)}
            <li class="flex flex-col rounded-3xl border bg-paper-50 p-3 transition-opacity {pending === `${d.id}:delete` ? 'opacity-50' : ''}" aria-busy={pending.startsWith(d.id)}>
              <img src={d.thumbnail} alt="" class="aspect-square w-full rounded-2xl bg-white object-contain p-4" />
              <div class="mt-3 flex items-start gap-1 px-1">
                <div class="min-w-0 flex-1">
                  <div class="truncate font-semibold">{d.name}.{d.format}</div>
                  <div class="text-sm text-muted-foreground">{Math.round(d.width_mm)} × {Math.round(d.height_mm)} mm · {new Date(d.created_at).toLocaleDateString()}</div>
                </div>
                <Button variant="ghost" size="icon-sm" aria-label="Download {d.name}" disabled={busy} onclick={() => download(d)}>{#if pending === `${d.id}:download`}<LoaderCircle aria-hidden="true" class="animate-spin" />{:else}<Download aria-hidden="true" />{/if}</Button>
                <Button variant="ghost" size="icon-sm" aria-label="Delete {d.name}" disabled={busy} onclick={() => remove(d)}>{#if pending === `${d.id}:delete`}<LoaderCircle aria-hidden="true" class="animate-spin" />{:else}<Trash2 aria-hidden="true" />{/if}</Button>
              </div>
              <ul class="mt-2 flex flex-wrap gap-1 px-1" aria-label="Threads">
                {#each d.threads as t (t.id)}
                  <li class="size-5 rounded-full border border-black/15" style="background: {t.hex}" title="{t.name} · {t.brand} {t.code}"></li>
                {/each}
              </ul>
            </li>
          {/each}
        </ul>
      {:else if designs}
        <p class="mt-6 rounded-2xl bg-paper-100 p-4">Nothing saved yet. Make a design, then choose <strong>Save to my designs</strong> on the Sew tab.</p>
      {:else if busy}
        <p class="mt-6 flex items-center gap-2 text-muted-foreground"><LoaderCircle aria-hidden="true" class="size-5 animate-spin" /> Loading your designs…</p>
      {/if}
    {/if}

    {#if error}<p role="alert" class="mt-5 rounded-2xl bg-ink-950 px-4 py-3 text-white">{error}</p>{/if}
  </main>
</div>

<AccountDialog bind:this={accountDialog} />
