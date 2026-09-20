import { ArrowRight, Check, Pause, Play, Server, WalletCards } from "lucide-react";
import { ScrollReveal, SplitText } from "../reactbits";
import Icon from "../ui/Icon";
import { FEATURES } from "../../data/site";

function MiniPanel({ children, className = "" }) {
  return (
    <div className={`rounded-2xl border border-ink/10 bg-cream-50/75 p-4 ${className}`}>
      {children}
    </div>
  );
}

function FeatureVisual({ type }) {
  if (type === "hub") {
    return (
      <div className="grid grid-cols-3 gap-2">
        {["L4", "3.12", "Jupyter"].map((value, index) => (
          <MiniPanel key={value}>
            <p className="font-mono text-[11px] uppercase tracking-wide text-ink-faint">
              {["compute", "runtime", "action"][index]}
            </p>
            <p className="mt-2 truncate font-mono text-sm font-semibold text-ink">{value}</p>
          </MiniPanel>
        ))}
        <div className="col-span-3 flex items-center gap-3 rounded-2xl bg-ink px-4 py-3 text-white">
          <span className="h-2 w-2 animate-pulse rounded-full bg-signal-lime" />
          <span className="font-mono text-[13px] text-white/75">session ready</span>
          <span className="ml-auto font-mono text-xs text-brand-300">open URL →</span>
        </div>
      </div>
    );
  }
  if (type === "lifecycle") {
    return (
      <div className="flex items-center gap-2">
        <MiniPanel className="flex-1 bg-emerald-50/80">
          <Play size={14} className="text-emerald-600" />
          <p className="mt-2 font-mono text-xs font-semibold text-emerald-800">running</p>
        </MiniPanel>
        <ArrowRight size={14} className="shrink-0 text-ink-faint" />
        <MiniPanel className="flex-1 bg-brand-50/80">
          <Pause size={14} className="text-brand-600" />
          <p className="mt-2 font-mono text-xs font-semibold text-brand-800">snapshot</p>
        </MiniPanel>
        <ArrowRight size={14} className="shrink-0 text-ink-faint" />
        <MiniPanel className="flex-1">
          <span className="block h-3.5 w-3.5 rounded-full border-2 border-ink-faint" />
          <p className="mt-2 font-mono text-xs font-semibold text-ink-muted">$0 idle</p>
        </MiniPanel>
      </div>
    );
  }
  if (type === "managed") {
    return (
      <MiniPanel className="bg-[#202124] text-white">
        <div className="flex items-center gap-2 border-b border-white/10 pb-2 font-mono text-[11px] text-white/50">
          <span className="h-2 w-2 rounded-full bg-brand-400" /> extension storage / cli
        </div>
        <div className="mt-3 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-brand-500 font-mono text-xs font-bold">v3</span>
          <div>
            <p className="font-mono text-xs text-white/85">m-gpux 3.0.0</p>
            <p className="font-mono text-[11px] text-signal-lime">✓ managed · ready</p>
          </div>
        </div>
      </MiniPanel>
    );
  }
  if (type === "compose") {
    return (
      <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-center gap-2">
        {["web", "api", "worker"].map((name, index) => (
          <div key={name} className="contents">
            <MiniPanel className="text-center">
              <Server size={15} className="mx-auto text-brand-500" />
              <p className="mt-2 font-mono text-xs font-semibold text-ink">{name}</p>
              <p className="font-mono text-[10px] text-ink-faint">sandbox</p>
            </MiniPanel>
            {index < 2 && <span className="h-px w-3 bg-ink/20" />}
          </div>
        ))}
      </div>
    );
  }
  if (type === "serve") {
    return (
      <MiniPanel className="font-mono">
        <div className="flex items-center justify-between text-[11px] uppercase tracking-wide text-ink-faint">
          <span>endpoint</span><span className="text-emerald-600">200 live</span>
        </div>
        <p className="mt-3 truncate rounded-lg bg-ink px-3 py-2.5 text-xs text-signal-blue">
          https://m-gpux-api.modal.run/v1
        </p>
      </MiniPanel>
    );
  }
  return (
    <MiniPanel>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 font-mono text-xs text-ink-muted">
          <WalletCards size={14} /> monthly budget
        </span>
        <span className="font-mono text-xs font-semibold text-ink">$30.00</span>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-cream-200">
        <div className="h-full w-[42%] rounded-full bg-brand-grad" />
      </div>
      <p className="mt-2 flex items-center gap-1 font-mono text-[11px] text-emerald-700"><Check size={12} /> all profiles within budget</p>
    </MiniPanel>
  );
}

export default function FeaturesSection() {
  return (
    <section id="features" className="relative scroll-mt-24 py-20 sm:py-28">
      <div className="container-px">
        <div className="grid gap-8 lg:grid-cols-[.8fr_1.2fr] lg:items-end">
          <div>
            <span className="section-kicker">Product surface / v3</span>
            <h2 className="mt-5 max-w-xl font-display text-4xl font-semibold leading-[1.08] tracking-[-0.025em] text-ink sm:text-5xl">
              <SplitText text="One layer above raw infrastructure." />
            </h2>
          </div>
          <p className="max-w-2xl text-base leading-relaxed text-ink-muted lg:justify-self-end lg:text-lg">
            m-gpux keeps the flexibility of Modal, then adds the workflows teams repeat every day:
            safe profiles, durable state, guided deployment and a shared interface between terminal and editor.
          </p>
        </div>

        <div className="mt-12 grid auto-rows-fr gap-4 md:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature, index) => (
            <ScrollReveal
              key={feature.title}
              delay={(index % 3) * 0.06}
              className={feature.wide ? "lg:col-span-2" : ""}
            >
              <article className="group flex h-full flex-col overflow-hidden rounded-[1.6rem] border border-ink/10 bg-white/70 p-6 shadow-soft transition-all duration-300 hover:-translate-y-1 hover:border-ink/20 hover:bg-white hover:shadow-card sm:p-8">
                <div className="flex items-start justify-between gap-4">
                  <span className="grid h-12 w-12 place-items-center rounded-xl border border-ink/10 bg-cream-50 text-brand-600">
                    <Icon name={feature.icon} size={21} />
                  </span>
                  <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint">{feature.metric}</span>
                </div>
                <p className="eyebrow mt-6">{feature.eyebrow}</p>
                <h3 className="mt-2 font-display text-2xl font-semibold tracking-[-0.015em] text-ink">{feature.title}</h3>
                <p className="mt-3 max-w-xl text-base leading-7 text-ink-muted">{feature.body}</p>
                <div className="mt-auto pt-6">
                  <FeatureVisual type={feature.visual} />
                </div>
              </article>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  );
}
