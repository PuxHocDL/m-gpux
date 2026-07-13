import { ArrowRight, Github, Sparkles } from "lucide-react";
import { ScrollReveal, AuroraBackground, Magnet, ShinyText } from "../reactbits";
import CopyChip from "../ui/CopyChip";

const REPO = "https://github.com/PuxHocDL/m-gpux";

export default function CTASection() {
  return (
    <section className="container-px py-12">
      <ScrollReveal>
        <div className="relative overflow-hidden rounded-3xl border border-brand-200 bg-white/70 px-6 py-16 text-center shadow-card backdrop-blur-xl sm:px-12">
          <AuroraBackground className="opacity-80" />
          <div className="absolute inset-0 bg-dotgrid opacity-40 mask-fade-b" />
          <div className="relative z-10 mx-auto max-w-2xl">
            <p className="font-display text-sm font-bold uppercase tracking-[0.2em] text-brand-500">
              <ShinyText text="pip install m-gpux" />
            </p>
            <h2 className="mt-4 font-display text-3xl font-extrabold leading-tight tracking-tight text-ink sm:text-5xl">
              Ready to spin up your first GPU?
            </h2>
            <p className="mt-4 text-lg text-ink-soft">
              You already know the commands — you just typed them. Install m-gpux and run them for real.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Magnet>
                <a href="#tutorial" className="btn-primary text-base">
                  <Sparkles size={17} /> Replay the tutorial <ArrowRight size={16} />
                </a>
              </Magnet>
              <a href={REPO} target="_blank" rel="noreferrer" className="btn-ghost text-base">
                <Github size={17} /> Star on GitHub
              </a>
            </div>
            <div className="mt-6 flex justify-center">
              <CopyChip text="pip install m-gpux" />
            </div>
          </div>
        </div>
      </ScrollReveal>
    </section>
  );
}
