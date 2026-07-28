// Pure, presentational pieces split out of site.tsx — no "use client" needed (no
// interactivity), and deliberately zero server-only imports (getTranslations, src/lib/content.ts,
// etc.). site.tsx's server components (SiteHeader/WikiSidebar/SiteFooter) touch Node's `fs` via
// getDynamicNavigation; any client component that imported these from site.tsx instead of here
// would drag that into the browser bundle and fail with "Module not found: Can't resolve 'fs'".
import Link from "next/link";
import { ChevronRight } from "lucide-react";

export function Breadcrumbs({ items }: { items: { label: string; href?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-7 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`} className="flex items-center gap-2">
          {index > 0 && <ChevronRight className="h-4 w-4" />}
          {item.href ? <Link className="hover:text-foreground" href={item.href}>{item.label}</Link> : <span aria-current="page" className="text-foreground">{item.label}</span>}
        </span>
      ))}
    </nav>
  );
}

export function JsonLd({ data }: { data: unknown }) {
  const serialized = JSON.stringify(data).replace(/</g, "\\u003c");
  return <script type="application/ld+json" suppressHydrationWarning dangerouslySetInnerHTML={{ __html: serialized }} />;
}
