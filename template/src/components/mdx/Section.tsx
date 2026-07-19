export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="my-6">
      <h3 className="text-xl font-bold text-foreground">{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}
