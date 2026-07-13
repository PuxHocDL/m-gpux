import { motion } from "framer-motion";
import { ArrowRight, Github, Sparkles, Zap } from "lucide-react";
import {
  AuroraBackground,
  Particles,
  SplitText,
  GradientText,
  Magnet,
  StarBorder,
  TiltCard,
  Marquee,
} from "../reactbits";
import AutoTerminal from "../ui/AutoTerminal";
import CopyChip from "../ui/CopyChip";
import { GPUS, RUNTIMES } from "../../data/site";

const REPO = "https://github.com/PuxHocDL/m-gpux";

const HERO_SCRIPT = [
  {
    cmd: "m-gpux hub",
    output: [
      { tone: "accent", text: "? Compute › GPU · A10G   ? Action › Jupyter   ? Runtime › 3.12" },
      { tone: "warn", text: "⠿ Building image & starting Jupyter…" },
      { tone: "ok", text: "✔ Jupyter is live" },
      { tone: "url", text: "https://pux--m-gpux-hub-jupyter.modal.run" },
    ],
    pause: 2000,
  },
  {
    cmd: "m-gpux serve deploy",
    output: [
      { tone: "accent", text: "? Model › Qwen2.5-7B-Instruct   ? GPU › L4   ? Warm › 1" },
      { tone: "warn", text: "⠿ Deploying OpenAI-compatible API…" },
      { tone: "ok", text: "✔ Deployed in 12s" },
      { tone: "url", text: "https://pux--m-gpux-llm-api.modal.run/v1" },
    ],
    pause: 2000,
  },
];

function FloatingCard({ className, children, delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className={`absolute z-20 ${className}`}
    >
      <div className="animate-floaty rounded-2xl border border-line bg-white/90 px-4 py-3 shadow-card backdrop-blur-xl">
        {children}
      </div>
    </motion.div>
  );
}

export default function Hero() {
  return (
    <section id="top" className="relative overflow-hidden pt-28 sm:pt-36">
      <AuroraBackground />
      <Particles className="opacity-70" quantity={42} />
      <div className="absolute inset-0 bg-dotgrid opacity-[0.5] mask-fade-b" />

      <div className="container-px relative grid items-center gap-12 pb-16 lg:grid-cols-[1.05fr_1fr] lg:pb-24">
        {/* Left: copy */}
        <div className="relative z-10">
          <motion.span
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="pill"
          >
            <Zap size={13} className="fill-brand-500 text-brand-500" />
            v2.7.0 · Modal GPU Orchestrator
          </motion.span>

          <h1 className="mt-5 font-display text-4xl font-extrabold leading-[1.05] tracking-tight text-ink sm:text-5xl lg:text-6xl">
            <SplitText text="Spin up GPUs." className="block" />
            <span className="block">
              <GradientText>Ship AI.</GradientText>{" "}
              <SplitText text="One terminal." delay={0.25} className="inline" />
            </span>
          </h1>

          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35, duration: 0.6 }}
            className="mt-6 max-w-xl text-lg leading-relaxed text-ink-soft"
          >
            <strong className="font-semibold text-ink">m-gpux</strong> is a professional, interactive
            hub & CLI for Modal. Manage profiles, launch GPU sessions, host apps, serve LLMs and
            watch your spend — then <em>learn it by doing</em> in the tutorial below.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5, duration: 0.6 }}
            className="mt-8 flex flex-wrap items-center gap-3"
          >
            <Magnet>
              <a href="#tutorial" className="btn-primary text-base">
                <Sparkles size={17} /> Start the tutorial <ArrowRight size={16} />
              </a>
            </Magnet>
            <StarBorder as="a" href={REPO} target="_blank" rel="noreferrer">
              <Github size={16} /> View on GitHub
            </StarBorder>
          </motion.div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.7, duration: 0.6 }}
            className="mt-6"
          >
            <CopyChip text="pip install m-gpux" />
          </motion.div>

          <div className="mt-10 max-w-md">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-faint">
              Any GPU · any runtime
            </p>
            <Marquee
              items={[...GPUS, ...RUNTIMES.map((r) => `py ${r}`)]}
              renderItem={(it) => (
                <span className="rounded-lg border border-line bg-white/70 px-3 py-1.5 font-mono text-xs text-ink-soft">
                  {it}
                </span>
              )}
            />
          </div>
        </div>

        {/* Right: live terminal + floating cards */}
        <div className="relative z-10">
          <TiltCard max={6}>
            <AutoTerminal script={HERO_SCRIPT} />
          </TiltCard>

          <FloatingCard className="-left-4 top-6 hidden sm:block" delay={0.7}>
            <div className="flex items-center gap-2.5">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-emerald-100 text-emerald-600">
                <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-500" />
              </span>
              <div className="leading-tight">
                <p className="font-mono text-xs font-semibold text-ink">A100 · live</p>
                <p className="text-[11px] text-ink-muted">session tracked</p>
              </div>
            </div>
          </FloatingCard>

          <FloatingCard className="-right-3 bottom-8 hidden sm:block" delay={0.9}>
            <div className="leading-tight">
              <p className="text-[11px] text-ink-muted">30-day spend · all profiles</p>
              <p className="font-display text-lg font-extrabold text-brand-600">$10.36</p>
            </div>
          </FloatingCard>
        </div>
      </div>
    </section>
  );
}
