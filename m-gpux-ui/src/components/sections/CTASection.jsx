import { ArrowRight, Github, MonitorDown, TerminalSquare } from "lucide-react";
import { ScrollReveal } from "../reactbits";
import CopyChip from "../ui/CopyChip";

const REPO = "https://github.com/PuxHocDL/m-gpux";
const MARKET = "https://marketplace.visualstudio.com/items?itemName=puxpux.m-gpux";

export default function CTASection() {
  return (
    <section id="get-started" className="container-px scroll-mt-24 py-14 sm:py-20">
      <ScrollReveal>
        <div className="relative overflow-hidden rounded-[2rem] border border-brand-900/20 bg-brand-800 px-6 py-12 text-white shadow-term sm:px-10 lg:px-14 lg:py-16">
          <div className="absolute inset-0 bg-dotgrid opacity-20" />
          <div className="absolute -right-20 -top-28 h-80 w-80 rounded-full bg-brand-300/20 blur-[100px]" />
          <div className="relative grid gap-10 lg:grid-cols-[.8fr_1.2fr] lg:items-end">
            <div>
              <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-brand-200">Start here / v3.0</p>
              <h2 className="mt-4 max-w-xl font-display text-5xl font-semibold leading-[1.02] tracking-[-0.02em] sm:text-6xl">
                Choose your surface. Keep the same state.
              </h2>
              <p className="mt-5 max-w-lg text-sm leading-relaxed text-white/55 sm:text-base">
                CLI and extension share profiles, presets, sessions and workspace state. Start in one,
                continue in the other.
              </p>
              <a href={REPO} target="_blank" rel="noreferrer" className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-white/75 hover:text-white">
                <Github size={16} /> Read the source <ArrowRight size={15} />
              </a>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-white/12 bg-white/[0.055] p-5 backdrop-blur">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-500"><TerminalSquare size={18} /></span>
                <h3 className="mt-5 font-display text-lg font-semibold">Install the CLI</h3>
                <p className="mt-1 text-xs leading-relaxed text-white/45">Python 3.10+ · Windows, macOS and Linux</p>
                <CopyChip text="pip install -U m-gpux" dark className="mt-5 w-full justify-between" />
              </div>

              <div className="rounded-2xl border border-white/12 bg-white/[0.055] p-5 backdrop-blur">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-200 text-brand-900"><MonitorDown size={18} /></span>
                <h3 className="mt-5 font-display text-lg font-semibold">Install the extension</h3>
                <p className="mt-1 text-xs leading-relaxed text-white/45">Managed CLI included · one-click setup</p>
                <a href={MARKET} target="_blank" rel="noreferrer" className="mt-5 flex w-full items-center justify-between rounded-xl border border-white/15 bg-white/[0.06] px-4 py-3 text-sm font-semibold text-white/85 hover:border-white/30 hover:bg-white/10">
                  Open Marketplace <ArrowRight size={15} />
                </a>
              </div>
            </div>
          </div>
        </div>
      </ScrollReveal>
    </section>
  );
}
