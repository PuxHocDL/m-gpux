import { CountUp, ScrollReveal, SpotlightCard } from "../reactbits";
import { STATS } from "../../data/site";

export default function StatsBand() {
  return (
    <section className="container-px py-6">
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {STATS.map((s, i) => (
          <ScrollReveal key={s.label} delay={i * 0.06}>
            <SpotlightCard className="card h-full px-5 py-6">
              <div className="font-display text-3xl font-extrabold text-gradient sm:text-4xl">
                {typeof s.value === "number" ? <CountUp to={s.value} suffix={s.suffix} /> : s.value}
              </div>
              <p className="mt-1 text-sm font-semibold text-ink">{s.label}</p>
              <p className="text-xs text-ink-muted">{s.hint}</p>
            </SpotlightCard>
          </ScrollReveal>
        ))}
      </div>
    </section>
  );
}
