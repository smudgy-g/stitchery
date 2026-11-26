<script lang="ts">
  import type { Snippet } from "svelte";
  import type { HTMLAttributes } from "svelte/elements";
  import type { Hoop } from "./picture";

  interface Props extends Omit<HTMLAttributes<HTMLDivElement>, "children"> {
    hoop: Hoop;
    /** 1 fits the whole hoop on screen */
    zoom?: number;
    hoopEl?: HTMLDivElement;
    /** Drawn inside the hoop, given screen pixels per mm */
    children: Snippet<[number]>;
  }
  let { hoop, zoom = 1, hoopEl = $bindable(), children, class: cls = "", ...rest }: Props = $props();

  let width = $state(0), height = $state(0);
  let scroller: HTMLDivElement;
  // Every tab uses this one scale, so the design stays the same size between tabs
  let k = $derived(zoom * Math.max(0.1, Math.min((width - 48) / hoop.w, (height - 48) / hoop.h)));

  // Zooming keeps the middle of the view in the middle
  $effect(() => {
    k;
    scroller.scrollLeft = (scroller.scrollWidth - scroller.clientWidth) / 2;
    scroller.scrollTop = (scroller.scrollHeight - scroller.clientHeight) / 2;
  });
</script>

<div bind:clientWidth={width} bind:clientHeight={height} class="relative size-full {cls}" {...rest}>
  <div bind:this={scroller} class="absolute inset-0 flex p-6 {zoom > 1 ? 'overflow-auto' : 'overflow-hidden'}">
    <div bind:this={hoopEl} class="preview-grid relative m-auto shrink-0 rounded-[2rem]" style="width:{hoop.w * k}px;height:{hoop.h * k}px">
      {@render children(k)}
    </div>
  </div>
</div>
