import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { ScrollReveal, SpotlightCard, SplitText } from "../reactbits";
import Icon from "../ui/Icon";
import { COMMAND_GROUPS } from "../../data/commands";

function CommandRow({ cmd, desc }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(true);
      setTimeout(() => setCopied(false), 1300);
    } catch {
      /* noop */
    }
  };
  return (
    <button
      onClick={copy}
      className="group/row flex w-full items-start gap-3 rounded-xl border border-transparent px-3 py-2 text-left transition-colors hover:border-line hover:bg-brand-50/50"
    >
      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-300" />
      <span className="min-w-0 flex-1">
        <code className="block truncate font-mono text-[13px] font-semibold text-ink">{cmd}</code>
        <span className="text-xs text-ink-muted">{desc}</span>
      </span>
      <span className="mt-0.5 shrink-0 text-ink-faint opacity-0 transition-opacity group-hover/row:opacity-100">
        {copied ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
      </span>
    </button>
  );
}

export default function CommandShowcase() {
  return (
    <section id="commands" className="relative scroll-mt-24 py-20 sm:py-28">
      <div className="container-px">
        <div className="mx-auto max-w-2xl text-center">
          <span className="pill mx-auto">9 command groups</span>
          <h2 className="mt-4 font-display text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">
            <SplitText text="The whole CLI, at a glance." />
          </h2>
          <p className="mt-4 text-ink-soft">
            Every workflow from the tutorial — and more. Hover a card, click any command to copy it.
          </p>
        </div>

        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {COMMAND_GROUPS.map((g, i) => (
            <ScrollReveal key={g.id} delay={(i % 3) * 0.07}>
              <SpotlightCard className="card h-full p-6">
                <div className="flex items-center gap-3">
                  <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-grad text-white shadow-soft">
                    <Icon name={g.icon} size={20} />
                  </span>
                  <h3 className="font-display text-lg font-bold text-ink">{g.title}</h3>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-ink-muted">{g.blurb}</p>
                <div className="mt-4 space-y-0.5">
                  {g.commands.map((c) => (
                    <CommandRow key={c.cmd} {...c} />
                  ))}
                </div>
              </SpotlightCard>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  );
}
