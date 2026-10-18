import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

function Input({ className, type, ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      className={cn("h-10 w-full min-w-0 rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-950 outline-none transition-colors placeholder:text-gray-400 focus-visible:border-sky-500 focus-visible:ring-2 focus-visible:ring-sky-500/20 disabled:opacity-50", className)}
      {...props}
    />
  );
}

export { Input };
