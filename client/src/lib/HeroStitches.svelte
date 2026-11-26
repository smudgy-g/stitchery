<script lang="ts">
  // Decorative: a hoop showing cross stitch, running stitch and satin stitch.
  const HEART = [".XX.XX.", "XXXXXXX", "XXXXXXX", ".XXXXX.", "..XXX..", "...X..."];
  const CELL = 14;
  const crosses = HEART.flatMap((row, y) => [...row].flatMap((c, x) => (c === "X" ? [{ x: 161 + x * CELL, y: 78 + y * CELL }] : [])));

  // Satin stitch: short slanted bars packed side by side along an arc
  const satin = Array.from({ length: 34 }, (_, i) => {
    const a = ((126 + i * 2.85) * Math.PI) / 180;
    const b = a + 0.05;
    return { x1: 210 + 104 * Math.cos(a), y1: 210 + 104 * Math.sin(a), x2: 210 + 126 * Math.cos(b), y2: 210 + 126 * Math.sin(b) };
  });
</script>

<svg viewBox="0 0 420 420" aria-hidden="true" class="w-full">
  <defs><clipPath id="hoop-fabric"><circle cx="210" cy="210" r="164" /></clipPath></defs>
  <circle cx="210" cy="210" r="164" fill="#fdfcfb" />
  <g clip-path="url(#hoop-fabric)" stroke-linecap="round" fill="none">
    {#each crosses as c (`${c.x},${c.y}`)}
      <path d="M{c.x + 3} {c.y + 3}l{CELL - 6} {CELL - 6}M{c.x + CELL - 3} {c.y + 3}l{6 - CELL} {CELL - 6}" class="stroke-amethyst-smoke-500" stroke-width="2.5" />
    {/each}
    <path d="M138 214C180 160 205 268 252 212S332 160 370 205" class="stroke-spicy-paprika-500" stroke-width="4" stroke-dasharray="13 9" />
    {#each satin as s, i (i)}
      <line x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} class="stroke-prussian-blue-600" stroke-width="3" />
    {/each}
  </g>
  <!-- Hoop: inner and outer ring, with the tightening screw at the top -->
  <circle cx="210" cy="210" r="166" fill="none" class="stroke-dust-grey-300" stroke-width="5" />
  <circle cx="210" cy="210" r="176" fill="none" class="stroke-dust-grey-400" stroke-width="10" />
  <rect x="196" y="16" width="28" height="24" rx="5" class="fill-dust-grey-500" />
  <!-- Loose thread and needle -->
  <path d="M370 205C400 170 396 120 360 92" fill="none" class="stroke-vintage-grape-500" stroke-width="2" stroke-linecap="round" />
  <path d="M352 104L398 42" class="stroke-dust-grey-600" stroke-width="3.5" stroke-linecap="round" />
</svg>
