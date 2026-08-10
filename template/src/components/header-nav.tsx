"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown, ChevronRight } from "lucide-react";
import { localizeHref } from "@/lib/locale-path";

export type HeaderNavItem = {
  key: string;
  path: string;
  label: string;
  /** Up to a handful of {label, href} article links to preview on hover — omit or leave empty to render a plain link with no dropdown. */
  articles?: { label: string; href: string }[];
  readMoreLabel?: string;
};

export function HeaderNavLinks({
  items,
  locale,
  className,
  linkClassName,
  activeClassName,
  onNavigate,
}: {
  items: HeaderNavItem[];
  locale: string;
  className?: string;
  linkClassName: string;
  activeClassName: string;
  onNavigate?: () => void;
}) {
  const pathname = usePathname() ?? "/";
  const [openKey, setOpenKey] = useState<string | null>(null);

  const isActive = (path: string) => {
    const localized = localizeHref(path, locale);
    return pathname === localized || pathname.startsWith(`${localized}/`);
  };

  return (
    <nav className={className}>
      {items.map((item) => {
        const hasPreview = item.articles && item.articles.length > 0;
        const isOpen = openKey === item.key;
        return (
          <div
            key={item.key}
            className="relative flex h-full items-center"
            onMouseEnter={() => hasPreview && setOpenKey(item.key)}
            onMouseLeave={() => setOpenKey((current) => (current === item.key ? null : current))}
            onFocus={() => hasPreview && setOpenKey(item.key)}
            onBlur={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget)) setOpenKey((current) => (current === item.key ? null : current));
            }}
          >
            <Link href={localizeHref(item.path, locale)} onClick={onNavigate} className={`${linkClassName} ${isActive(item.path) ? activeClassName : ""} flex items-center gap-1`}>
              {item.label}
              {hasPreview && <ChevronDown className={`h-3 w-3 transition-transform ${isOpen ? "rotate-180" : ""}`} aria-hidden="true" />}
            </Link>
            {hasPreview && isOpen && (
              <div className="absolute left-0 top-full z-50 w-64 overflow-hidden rounded-xl border border-border bg-card shadow-xl">
                <div className="py-2">
                  {item.articles!.slice(0, 5).map((article) => (
                    <Link key={article.href} href={localizeHref(article.href, locale)} onClick={onNavigate} className="block truncate px-4 py-2 text-sm text-foreground hover:bg-muted">
                      {article.label}
                    </Link>
                  ))}
                </div>
                <Link href={localizeHref(item.path, locale)} onClick={onNavigate} className="flex items-center justify-center gap-1 border-t border-border py-2.5 text-sm font-semibold text-[hsl(var(--nav-theme))] hover:bg-muted">
                  {item.readMoreLabel ?? "Read more"} <ChevronRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}
