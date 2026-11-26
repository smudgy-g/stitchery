import adapter from "@sveltejs/adapter-static";

/** @type {import('@sveltejs/kit').Config} */
export default {
  // Single-page app: Caddy serves index.html for every path
  kit: { adapter: adapter({ fallback: "index.html" }) },
};
