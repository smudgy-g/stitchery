<script lang="ts">
  import { Input } from "$lib/components/ui/input";
  import type { Thread } from "./api";
  import { threadOrder } from "./colours";

  let { threads, value, onpick }: { threads: Thread[]; value?: string; onpick: (t: Thread) => void } = $props();

  let brand = $state("");
  let query = $state("");
  let sorted = $derived([...threads].sort((a, b) => threadOrder(a) - threadOrder(b)));
  let shown = $derived(sorted.filter((t) => (!brand || t.brand === brand) && `${t.name} ${t.code}`.toLowerCase().includes(query.trim().toLowerCase())));
</script>

<div class="space-y-3 rounded-2xl bg-background p-3">
  <div class="flex gap-2">
    <Input bind:value={query} placeholder="Search threads" aria-label="Search threads by name or number" class="h-10" />
    <select bind:value={brand} aria-label="Thread brand" class="h-10 rounded-full border border-input bg-card px-3">
      <option value="">All</option>
      {#each ["Brother", "Janome", "Husqvarna"] as b (b)}<option>{b}</option>{/each}
    </select>
  </div>
  <div class="grid max-h-56 grid-cols-[repeat(auto-fill,minmax(2rem,1fr))] gap-1.5 overflow-y-auto p-0.5" role="listbox" aria-label="Threads">
    {#each shown as t (t.id)}
      <button
        type="button"
        role="option"
        aria-selected={t.id === value}
        title="{t.name} · {t.brand} {t.code}"
        aria-label="{t.name}, {t.brand} {t.code}"
        class="aspect-square rounded-full border border-black/15 transition-transform hover:scale-110 aria-selected:ring-3 aria-selected:ring-vermilion-500"
        style="background:{t.hex}"
        onclick={() => onpick(t)}
      ></button>
    {:else}
      <p class="col-span-full text-muted-foreground">No threads match.</p>
    {/each}
  </div>
</div>
