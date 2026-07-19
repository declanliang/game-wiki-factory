"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

interface CollapsibleNavGroupProps {
  title: string;
  icon: React.ReactNode;
  count?: number;
  defaultOpen?: boolean;
  currentPath?: string;
  children: React.ReactNode;
}

export function CollapsibleNavGroup({ title, icon, count, defaultOpen, currentPath, children }: CollapsibleNavGroupProps) {
  // Auto-open if currentPath matches a link in this group
  const shouldOpen = defaultOpen ?? (currentPath ? hasMatchingLink(children, currentPath) : false);
  const [open, setOpen] = useState(shouldOpen);

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="mb-2 flex w-full items-center gap-2 text-sm font-semibold text-foreground"
      >
        {icon}
        <span>{title}</span>
        {count !== undefined && <span className="ml-1 text-xs text-muted-foreground">({count})</span>}
        <ChevronDown className={`ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && children}
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
