"use client";

import { useId, useState } from "react";
import { ChevronDown, X } from "lucide-react";

interface Heading {
  id: string;
  text: string;
  level: number;
}

/**
 * 标题和正文之间显示的可折叠 TOC 面板，所有屏幕宽度下都显示——文章页不再有常驻的
 * 桌面端侧边栏（顶部导航已经覆盖了站点级导航，长文章的页内导航靠这个面板，不靠一个
 * 只在大屏幕才出现的侧边栏）。
 */
export function MobileTOC({ headings, label }: { headings: Heading[]; label: string }) {
  const [open, setOpen] = useState(false);
  const contentId = useId();
  const sectionHeadings = headings.filter((heading) => heading.level === 2);

  // 只在分段较多时才启用 TOC（避免短文章出现形式大于内容的冗余目录）
  if (sectionHeadings.length < 4) return null;

  return (
    <div className="mt-6 mb-6 rounded-2xl border border-border bg-card/70 p-4">
      <div className="flex items-center justify-between">
        <button
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          aria-controls={contentId}
          className="flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-muted-foreground"
        >
          <ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} />
          {label}
        </button>
        {open && (
          <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground" aria-label="Close TOC">
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      {open && (
        <nav id={contentId} aria-label={label} className="mt-3 space-y-1 border-t border-border pt-3">
          {sectionHeadings.map((h) => (
            <a
              key={h.id}
              href={`#${h.id}`}
              onClick={() => setOpen(false)}
              className="block rounded-lg px-2 py-1.5 text-sm text-muted-foreground transition hover:bg-muted hover:text-foreground"
            >
              {h.text}
            </a>
          ))}
        </nav>
      )}
    </div>
  );
}
