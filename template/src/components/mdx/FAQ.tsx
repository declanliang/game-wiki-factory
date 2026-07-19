export function FAQ({ question, children }: { question: string; children: React.ReactNode }) {
  return (
    <div className="my-4 rounded-lg border border-border bg-card/70 p-4">
      <h4 className="font-bold text-foreground">{question}</h4>
      <div className="mt-2 text-sm text-muted-foreground">{children}</div>
    </div>
  );
}
