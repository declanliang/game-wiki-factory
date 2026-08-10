"use client";

import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";

interface CollapsibleNavGroupProps {
  title: string;
  icon: React.ReactNode;
  count?: number;
  defaultOpen?: boolean;
  active?: boolean;
  currentPath?: string;
  children: React.ReactNode;
}

export function CollapsibleNavGroup({ title, icon, count, defaultOpen, active = false, currentPath, children }: CollapsibleNavGroupProps) {
  // Auto-open if currentPath matches a link in this group
  const shouldOpen = defaultOpen ?? (currentPath ? hasMatchingLink(children, currentPath) : false);
  const [open, setOpen] = useState(shouldOpen);
  const contentId = useId();

  return (
    <div
      className={`rounded-2xl border transition-colors ${
        active
          ? "border-[hsl(var(--nav-theme)/0.42)] bg-[hsl(var(--nav-theme)/0.08)]"
          : "border-border/70 bg-background/35 hover:border-border"
      }`}
    >
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={contentId}
        className="flex w-full items-center gap-3 px-3 py-3 text-left text-sm font-semibold text-foreground"
      >
        {icon}
        <span className="min-w-0 flex-1">
          <span className="block truncate">{title}</span>
          {count !== undefined && (
            <span className="mt-0.5 block text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
              {count}
            </span>
          )}
        </span>
        <ChevronDown className={`ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div id={contentId} className="px-2 pb-3">{children}</div>}
    </div>
  );
}

/** Check if any <Link href="..."> inside children matches currentPath */
function hasMatchingLink(children: React.ReactNode, currentPath: string): boolean {
  if (!children) return false;
  if (Array.isArray(children)) return children.some((c) => hasMatchingLink(c, currentPath));
  if (typeof children === "object" && children !== null && "props" in children) {
    const props = (children as React.ReactElement).props;
    const href = props.href as string | undefined;
    if (href && (href === currentPath || currentPath.startsWith(href + "/"))) return true;
    if (props.children) return hasMatchingLink(props.children, currentPath);
  }
  return false;
}
