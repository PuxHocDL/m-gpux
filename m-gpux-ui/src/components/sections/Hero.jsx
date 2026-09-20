import { motion } from "framer-motion";
import { ArrowRight, Github, Search, ShieldCheck, Sparkles } from "lucide-react";
import { Magnet, Marquee } from "../reactbits";
import AutoTerminal from "../ui/AutoTerminal";
import CopyChip from "../ui/CopyChip";
import { GPUS } from "../../data/site";

const REPO = "https://github.com/PuxHocDL/m-gpux";

const HERO_SCRIPT = [
  {
    cmd: "m-gpux dev up --name studio",
    output: [
      { tone: "accent", text: "Compute  GPU · L4    Workspace  ./studio" },
      { tone: "warn", text: "◌ Building image and starting Sandbox..." },
      { tone: "ok", text: "✓ Dev box 'studio' is ready · auto-stop 12h" },
      { tone: "url", text: "ssh m-gpux-studio" },
    ],
    pause: 2100,
  },
  {
    cmd: "m-gpux dev pause studio",
    output: [
      { tone: "warn", text: "◌ Snapshotting packages + /workspace..." },
      { tone: "ok", text: "✓ Paused · compute billing stopped" },
      { tone: "dim", text: "Resume later with: m-gpux dev resume studio" },
    ],
    pause: 2100,
  },
];

function Signal({ label, value, active = false }) {
  return (
    <div className="rounded-xl border border-ink/10 bg-cream-50/70 p-3">
      <p className="font-mono text-[9px] uppercase tracking-[0.16em] text-ink-faint">{label}</p>
      <div className="mt-2 flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${active ? "bg-brand-500 shadow-[0_0_12px_rgba(0,122,94,.45)]" : "bg-brand-300"}`} />
        <p className="truncate font-mono text-xs font-semibold text-ink">{value}</p>
      </div>
    </div>
  );
}

function ControlDeck() {
  return (
    <motion.div
      initial={false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      className="relative min-w-0"
    >
      <div className="absolute -inset-10 rounded-full bg-brand-200/40 blur-3xl" />
      <div className="relative overflow-hidden rounded-[1.5rem] border border-ink/10 bg-white/85 p-3 shadow-card backdrop-blur-xl sm:p-4">
        <div className="flex items-center justify-between px-2 pb-3 pt-1">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-brand-500 shadow-[0_0_14px_rgba(0,122,94,.55)]" />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-muted">
              control / tool1
            </span>
          </div>
          <span className="rounded-md border border-brand-200 bg-brand-50 px-2 py-1 font-mono text-[9px] text-brand-700">live</span>
        </div>

        <div className="mb-3 grid grid-cols-3 gap-2">
          <Signal label="runtime" value="modal 1.5" />
          <Signal label="compute" value="L4 · ready" active />
          <Signal label="budget" value="$24.82 left" />
        </div>

        <AutoTerminal script={HERO_SCRIPT} title="m-gpux — dev lifecycle" className="shadow-none" />

        <div className="mt-3 flex items-center justify-between rounded-xl border border-ink/10 bg-cream-50/70 px-3 py-2.5">
          <span className="flex items-center gap-2 font-mono text-[10px] text-ink-muted">
            <ShieldCheck size={13} className="text-brand-600" /> profile pinned · state persisted
          </span>
          <span className="font-mono text-[10px] text-ink-faint">v3.0.0</span>
        </div>
      </div>
    </motion.div>
  );
}

export default function Hero() {
  return (
    <section id="top" className="relative overflow-hidden border-b border-ink/10 pt-[68px]">
      <div className="grid-scan absolute inset-0 bg-dotgrid opacity-45" aria-hidden="true" />
      <div className="container-px relative py-16 sm:py-24 lg:py-28">
        <div className="grid min-w-0 items-center gap-14 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,.95fr)] xl:gap-20">
          <div className="relative z-10 min-w-0">
            <motion.p
              initial={false}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-3 font-mono text-[11px] font-medium uppercase tracking-[0.22em] text-ink-muted"
            >
              <span className="h-2 w-2 rounded-full bg-brand-500" /> Modal workloads · one control plane
            </motion.p>

            <h1 className="mt-8 max-w-4xl font-display text-[clamp(3.7rem,7.2vw,7.2rem)] leading-[0.94] tracking-[-0.025em] text-ink">
              Run GPU infrastructure
              <span className="mt-2 block italic text-brand-600">without the drag.</span>
            </h1>

            <motion.p
              initial={false}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15, duration: 0.6 }}
              className="mt-8 max-w-2xl text-balance text-base leading-relaxed text-ink-muted sm:text-lg"
            >
              Launch sessions, operate Sandbox dev boxes, deploy Compose stacks and track every
              profile—from one CLI or directly inside VS Code.
            </motion.p>

            <motion.div
              initial={false}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.28, duration: 0.6 }}
              className="mt-9 max-w-2xl rounded-2xl border border-ink/10 bg-white/85 p-2 shadow-soft backdrop-blur"
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <div className="flex min-w-0 flex-1 items-center gap-3 px-3">
                  <Search size={19} className="shrink-0 text-ink-faint" />
                  <CopyChip text="pip install -U m-gpux" className="border-0 bg-transparent p-0 shadow-none hover:border-0" />
                </div>
                <Magnet>
                  <a href="/docs/" className="btn-primary w-full px-7 sm:w-auto">
                    Read the docs <ArrowRight size={17} />
                  </a>
                </Magnet>
              </div>
            </motion.div>

            <div className="mt-6 flex flex-wrap items-center gap-5 text-sm font-medium text-ink-muted">
              <a href="#get-started" className="inline-flex items-center gap-2 transition-colors hover:text-brand-700">
                <Sparkles size={15} /> Get m-gpux <ArrowRight size={14} />
              </a>
              <a href={REPO} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 transition-colors hover:text-brand-700">
                <Github size={16} /> GitHub
              </a>
            </div>
          </div>

          <ControlDeck />
        </div>

        <div className="relative mt-16 border-t border-ink/10 pt-5">
          <div className="grid gap-4 md:grid-cols-[auto_1fr] md:items-center">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">provision any compute</p>
            <Marquee
              items={GPUS}
              renderItem={(item) => (
                <span className="rounded-lg border border-ink/10 bg-white/65 px-3 py-1.5 font-mono text-[10px] text-ink-muted">
                  {item}
                </span>
              )}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
