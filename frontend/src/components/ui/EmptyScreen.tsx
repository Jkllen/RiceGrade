type EmptyScreenProps = { title: string; description: string };

export function EmptyScreen({ title, description }: EmptyScreenProps) {
  return (
    <section className="rounded-xl border border-stone-200 bg-white p-6" aria-label={title}>
      <h2 className="text-2xl font-semibold text-stone-900">{title}</h2>
      <p className="mt-2 text-stone-600">{description}</p>
      <div className="mt-6 rounded-lg border border-dashed border-stone-300 bg-stone-50 p-5">
        <p className="text-sm font-medium text-stone-600">Screen scaffold only</p>
        <p className="mt-1 text-sm text-stone-500">No records, measurements, classifications, or recommendations are available yet.</p>
      </div>
    </section>
  );
}
