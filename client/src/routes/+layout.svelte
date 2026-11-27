<script lang="ts">
  import { onMount } from "svelte";
  import { account, refreshAccount } from "$lib/account.svelte";
  import "../app.css";

  let { children } = $props();

  onMount(() => {
    refreshAccount().catch(() => (account.ready = true));
  });
</script>

{@render children()}
