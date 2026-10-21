import {
  Activity,
  ArrowRight,
  Box,
  Check,
  ChevronDown,
  CircleDollarSign,
  Cloud,
  Code2,
  Cpu,
  Layers3,
  Play,
  Plus,
  RefreshCw,
  Server,
  Settings,
  TerminalSquare,
} from "lucide-react";
import { ScrollReveal, SplitText, Magnet } from "../reactbits";
import { EXTENSION_HIGHLIGHTS } from "../../data/extension";

const MARKET = "https://marketplace.visualstudio.com/items?itemName=puxpux.m-gpux";

function SectionTitle({ children, action }) {
  return (
    <div className="flex items-center justify-between px-3 py-2 text-[10px] font-bold uppercase tracking-[0.08em] text-[#bbb]">
      <span className="flex items-center gap-1"><ChevronDown size={11} />{children}</span>
      {action}
    </div>
  );
}

function ExtensionWindow() {
  const quickActions = [
    [Cpu, "GPU Hub"],
    [Box, "Dev Box"],
    [Layers3, "Compose"],
    [Server, "Serve"],
  ];
  return (
    <div className="overflow-hidden rounded-[1.5rem] border border-black/30 bg-[#181818] shadow-term">
      <div className="flex h-10 items-center border-b border-black/50 bg-[#2b2b2b] px-3">
        <div className="flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-brand-300" />
          <span className="h-2.5 w-2.5 rounded-full bg-brand-500" />
          <span className="h-2.5 w-2.5 rounded-full bg-brand-700" />
        </div>
        <p className="mx-auto font-sans text-[11px] text-[#b7b7b7]">studio — Visual Studio Code</p>
        <span className="w-10" />
      </div>

      <div className="grid min-h-[480px] grid-cols-[44px_220px_1fr] sm:grid-cols-[48px_245px_1fr]">
        <aside className="flex flex-col items-center border-r border-[#292929] bg-[#202020] py-3 text-[#858585]">
          {[Code2, Cloud, Box, Layers3].map((Icon, index) => (
            <span key={index} className={`relative mb-2 grid h-9 w-9 place-items-center ${index === 1 ? "text-white" : ""}`}>
              {index === 1 && <span className="absolute -left-1.5 h-7 w-0.5 bg-brand-400" />}
              <Icon size={20} />
            </span>
          ))}
          <span className="mt-auto grid h-9 w-9 place-items-center"><Settings size={19} /></span>
        </aside>

        <aside className="border-r border-[#292929] bg-[#232323] text-[#d4d4d4]">
          <div className="flex h-9 items-center justify-between px-4 text-[10px] uppercase tracking-wider text-[#c8c8c8]">
            <span>M-GPUX</span><span className="text-[#777]">•••</span>
          </div>

          <SectionTitle action={<Plus size={12} />}>Accounts</SectionTitle>
          <div className="mx-2 rounded bg-[#303030] px-3 py-2">
            <div className="flex items-center gap-2 text-[11px]">
              <span className="h-2 w-2 rounded-full bg-[#89d185]" />
              <span className="font-semibold text-white">tool1</span>
              <span className="ml-auto font-mono text-[9px] text-[#89d185]">active</span>
            </div>
            <p className="ml-4 mt-1 font-mono text-[9px] text-[#888]">$24.82 remaining</p>
          </div>

          <SectionTitle action={<RefreshCw size={11} />}>Active sessions</SectionTitle>
          <div className="space-y-1 px-2">
            <div className="border-l-2 border-brand-400 bg-[#2a2d2e] px-3 py-2">
              <div className="flex items-center gap-2 text-[10px] text-white"><Box size={12} />studio</div>
              <p className="mt-1 font-mono text-[8px] text-[#89d185]">● running · L4</p>
            </div>
            <div className="px-3 py-2">
              <div className="flex items-center gap-2 text-[10px]"><Server size={12} />llm-api</div>
              <p className="mt-1 font-mono text-[8px] text-[#75beff]">◆ deployed · idle</p>
            </div>
          </div>

          <SectionTitle>Quick actions</SectionTitle>
          <div className="grid grid-cols-2 gap-1.5 px-2">
            {quickActions.map(([Icon, label]) => (
              <div key={label} className="rounded border border-[#3b3b3b] bg-[#2a2a2a] p-2 text-[9px] text-[#c8c8c8]">
                <Icon size={12} className="mb-1.5 text-brand-300" />{label}
              </div>
            ))}
          </div>
        </aside>

        <main className="relative hidden overflow-hidden bg-[#1e1e1e] p-5 sm:block">
          <div className="absolute inset-0 opacity-[0.035] bg-dotgrid" />
          <div className="relative mx-auto mt-5 max-w-md">
            <p className="font-mono text-[9px] uppercase tracking-[0.16em] text-[#777]">M-GPUX / ENVIRONMENT</p>
            <h3 className="mt-2 font-display text-2xl font-semibold tracking-tight text-white">Ready without global installs.</h3>
            <p className="mt-2 text-[11px] leading-relaxed text-[#9c9c9c]">
              The extension created a private Python environment and loaded the bundled CLI.
            </p>

            <div className="mt-5 overflow-hidden rounded-xl border border-[#3a3a3a] bg-[#252526]">
              <div className="flex items-center gap-2 border-b border-[#3a3a3a] px-3 py-2 font-mono text-[9px] text-[#888]">
                <TerminalSquare size={12} /> CLI SETUP
              </div>
              <div className="space-y-3 p-4 font-mono text-[10px]">
                <div className="flex items-center justify-between text-[#ccc]"><span>m-gpux</span><span className="text-[#89d185]">3.0.0 ✓</span></div>
                <div className="flex items-center justify-between text-[#ccc]"><span>modal</span><span className="text-[#89d185]">1.5.5 ✓</span></div>
                <div className="h-px bg-[#393939]" />
                <p className="text-[#777]">scope: extension global storage</p>
              </div>
            </div>

            <button className="mt-4 inline-flex items-center gap-2 rounded-md bg-[#0e639c] px-3 py-2 text-[10px] font-semibold text-white">
              <Play size={12} /> Create dev box
            </button>
          </div>

          <div className="absolute bottom-4 right-4 w-56 rounded-md border border-[#454545] bg-[#252526] p-3 shadow-2xl">
            <p className="flex items-center gap-2 text-[10px] font-semibold text-white"><Check size={13} className="text-[#89d185]" /> CLI is ready</p>
            <p className="mt-1 text-[9px] leading-relaxed text-[#999]">The extension will manage updates automatically.</p>
          </div>
        </main>
      </div>

      <div className="flex h-6 items-center gap-3 bg-[#007acc] px-2.5 font-mono text-[8px] text-white/90">
        <span className="flex items-center gap-1"><Cloud size={9} /> tool1</span>
        <span className="flex items-center gap-1"><Activity size={9} /> Modal ready</span>
        <span className="ml-auto flex items-center gap-1"><CircleDollarSign size={9} /> $5.18 used</span>
      </div>
    </div>
  );
}

export default function ExtensionShowcase() {
  return (
    <section id="extension" className="relative scroll-mt-24 py-20 sm:py-28">
      <div className="container-px grid items-center gap-12 lg:grid-cols-[.82fr_1.18fr] xl:gap-20">
        <ScrollReveal>
          <span className="section-kicker">VS Code extension · v3.0</span>
          <h2 className="mt-5 max-w-xl font-display text-4xl font-semibold leading-[1.08] tracking-[-0.025em] text-ink sm:text-5xl">
            <SplitText text="Your Modal control room," />
            <span className="block text-brand-600">inside the editor.</span>
          </h2>
          <p className="mt-5 max-w-lg text-base leading-relaxed text-ink-muted">
            The extension is a first-class interface, not a thin launcher. It manages accounts,
            sessions, files, billing and the entire Dev Box lifecycle—and now bootstraps its own CLI.
          </p>
          <ul className="mt-7 space-y-3">
            {EXTENSION_HIGHLIGHTS.map((highlight) => (
              <li key={highlight} className="flex items-start gap-3 text-sm leading-relaxed text-ink-soft">
                <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-ink text-signal-lime">
                  <Check size={12} />
                </span>
                {highlight}
              </li>
            ))}
          </ul>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Magnet>
              <a href={MARKET} target="_blank" rel="noreferrer" className="btn-primary">
                Get the extension <ArrowRight size={16} />
              </a>
            </Magnet>
            <code className="rounded-xl border border-ink/10 bg-white/70 px-4 py-2.5 font-mono text-xs text-ink-muted shadow-soft">
              code --install-extension puxpux.m-gpux
            </code>
          </div>
        </ScrollReveal>

        <ScrollReveal delay={0.1}>
          <ExtensionWindow />
        </ScrollReveal>
      </div>
    </section>
  );
}
