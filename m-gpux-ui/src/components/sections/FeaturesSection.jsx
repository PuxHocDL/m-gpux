import { ScrollReveal, SpotlightCard, TiltCard, SplitText } from "../reactbits";
import Icon from "../ui/Icon";
import { FEATURES } from "../../data/site";

export default function FeaturesSection() {
  return (
    <section id="features" className="relative scroll-mt-24 py-20 sm:py-28">
      <div className="container-px">
        <div className="mx-auto max-w-2xl text-center">
          <span className="pill mx-auto">Why m-gpux</span>
          <h2 className="mt-4 font-display text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">
            <SplitText text="Everything Modal, orchestrated." />
          </h2>
          <p className="mt-4 text-ink-soft">
            One tool from first token to shipped endpoint — built for power users who live in the terminal.
          </p>
        </div>

        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <ScrollReveal key={f.title} delay={(i % 3) * 0.07}>
              <TiltCard max={7} className="h-full">
                <SpotlightCard className="card h-full p-6">
                  <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-50 text-brand-600 ring-1 ring-brand-100">
                    <Icon name={f.icon} size={22} />
                  </span>
                  <h3 className="mt-4 font-display text-lg font-bold text-ink">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-ink-muted">{f.body}</p>
                </SpotlightCard>
              </TiltCard>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  );
}
