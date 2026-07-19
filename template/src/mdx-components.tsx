import Link from "next/link";
import type { MDXComponents } from "mdx/types";
import { Info, Lightbulb, TriangleAlert, CircleCheck } from "lucide-react";

function toHeadingId(children: React.ReactNode): string {
  const text = String(children).replace(/<[^>]*>/g, "").trim();
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

const CALLOUT_STYLES = {
  info: { icon: Info, className: "callout-info" },
  tip: { icon: Lightbulb, className: "callout-tip" },
  warning: { icon: TriangleAlert, className: "callout-warning" },
  success: { icon: CircleCheck, className: "callout-success" },
} as const;

// Optional — content isn't required to use this. Available to MDX as <Callout type="tip">...</Callout>
// without an import (registered globally below), for the rare article that wants a highlighted aside.
function Callout({ type = "info", children }: { type?: keyof typeof CALLOUT_STYLES; children: React.ReactNode }) {
  const { icon: Icon, className } = CALLOUT_STYLES[type];
  return (
    <div className={`callout ${className}`}>
      <Icon className="callout-icon" />
      <div>{children}</div>
    </div>
  );
}

export function useMDXComponents(components: MDXComponents): MDXComponents {
  return {
    ...defaultComponents,
    ...components,
  };
}

// Most tag-level styling (size, color, spacing, list markers, code chips, etc.) lives in
// globals.css under the `.prose` rules, driven by @tailwindcss/typography — that's the single
// source of truth for how MDX content looks. This file only keeps what a typography plugin
// genuinely can't do: heading anchor IDs, next/link routing, and the table's card wrapper div.
const defaultComponents: MDXComponents = {
  h2: ({ children, id }) => <h2 id={id || toHeadingId(children)}>{children}</h2>,
  h3: ({ children, id }) => <h3 id={id || toHeadingId(children)}>{children}</h3>,
  a: ({ href = "", children }) => <Link href={href}>{children}</Link>,
  table: ({ children }) => (
    <div className="mt-9 mb-7 overflow-hidden rounded-xl border border-border bg-card">
      <table className="my-0 w-full text-sm">{children}</table>
    </div>
  ),
  Callout,
};
