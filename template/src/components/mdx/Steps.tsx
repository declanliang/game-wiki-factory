export function Steps({ children }: { children: React.ReactNode }) {
  return <ol className="my-4 list-decimal space-y-3 pl-6">{children}</ol>;
}

export function Step({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <li className="text-sm leading-7 text-muted-foreground">
      {title && <strong className="text-foreground">{title}</strong>}
      {children}
    </li>
  );
}
