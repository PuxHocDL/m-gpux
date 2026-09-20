import { ScrollReveal, SpotlightCard } from "../reactbits";
import { STATS } from "../../data/site";

export default function StatsBand() {
  return (
    <section className="container-px py-8 sm:py-10">
      <div className="grid grid-cols-2 overflow-hidden rounded-[1.5rem] border border-ink/10 bg-white/55 shadow-soft backdrop-blur lg:grid-cols-4">
        {STATS.map((s, i) => (
          <ScrollReveal key={s.label} delay={i * 0.06}>
            <SpotlightCard className={`h-full rounded-none px-5 py-6 shadow-none sm:px-7 ${i % 2 ? "border-l border-ink/10" : ""} ${i > 1 ? "border-t border-ink/10 lg:border-t-0" : ""} ${i > 0 ? "lg:border-l" : ""}`}>
              <div className="font-display text-3xl font-semibold tracking-[-0.02em] text-ink sm:text-4xl">
                {s.value}{s.suffix}
              </div>
              <p className="mt-1 text-sm font-bold text-ink">{s.label}</p>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-ink-faint">{s.hint}</p>
            </SpotlightCard>
          </ScrollReveal>
        ))}
      </div>
    </section>
  );
}
