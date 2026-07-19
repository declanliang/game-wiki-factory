export function CardGrid({ children }: { children: React.ReactNode }) {
  return <div className="my-4 grid gap-4 sm:grid-cols-2">{children}</div>;
}

export function Card({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card/70 p-4">
      {title && <h4 className="font-bold text-foreground">{title}</h4>}
      <div className="mt-2 text-sm text-muted-foreground">{children}</div>
    </div>
  );
}
