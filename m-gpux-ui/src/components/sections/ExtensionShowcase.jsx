import { useEffect, useState } from "react";
import { Check, Search, ArrowRight } from "lucide-react";
import { ScrollReveal, SplitText, Magnet } from "../reactbits";
import Icon from "../ui/Icon";
import { PALETTE_COMMANDS, EXTENSION_HIGHLIGHTS } from "../../data/extension";

const MARKET =
  "https://marketplace.visualstudio.com/items?itemName=PuxHocDL.m-gpux-vscode";

function CommandPalette() {
  const [active, setActive] = useState(0);
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    const id = setInterval(() => setActive((a) => (a + 1) % PALETTE_COMMANDS.length), 1600);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="overflow-hidden rounded-2xl border border-[#2b2b35] bg-[#1e1e1e] shadow-term">
      {/* VS Code title bar */}
      <div className="flex items-center gap-2 border-b border-black/40 bg-[#323233] px-4 py-2.5">
        <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
        <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
        <span className="h-3 w-3 rounded-full bg-[#28c840]" />
        <span className="mx-auto font-sans text-xs text-[#cfcfd2]">workspace — Visual Studio Code</span>
      </div>
      {/* Palette */}
      <div className="bg-[#1e1e1e] p-4">
        <div className="mx-auto max-w-xl rounded-md border border-[#454545] bg-[#252526] shadow-2xl">
          <div className="flex items-center gap-2 border-b border-[#3a3a3a] px-3 py-2.5">
            <Search size={14} className="text-[#a0a0a0]" />
            <span className="font-mono text-sm text-[#d4d4d4]">&gt;m-gpux</span>
            <span className="ml-0.5 inline-block h-4 w-[2px] animate-blink bg-brand-400" />
            <span className="ml-auto rounded bg-[#37373d] px-1.5 py-0.5 font-mono text-[10px] text-[#a0a0a0]">
              Ctrl ⇧ P
            </span>
          </div>
          <ul className="max-h-[320px] overflow-y-auto py-1">
            {PALETTE_COMMANDS.map((c, i) => (
              <li
                key={c.id}
                onMouseEnter={() => setActive(i)}
                className={`flex cursor-pointer items-center gap-3 px-3 py-2 ${
                  i === active ? "bg-[#094771]" : ""
                }`}
              >
                <span
                  className={`grid h-6 w-6 place-items-center rounded ${
                    i === active ? "bg-brand-500 text-white" : "bg-[#37373d] text-brand-300"
                  }`}
                >
                  <Icon name={c.icon} size={13} />
                </span>
                <span className="truncate font-sans text-[13px] text-[#e6e6e6]">{c.key}</span>
                <span className="ml-auto shrink-0 font-mono text-[10px] uppercase tracking-wide text-[#8a8a8a]">
                  {c.group}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

export default function ExtensionShowcase() {
  return (
    <section id="extension" className="relative scroll-mt-24 py-20 sm:py-28">
      <div className="container-px grid items-center gap-12 lg:grid-cols-[1fr_1.1fr]">
        <ScrollReveal>
          <span className="pill">VS Code extension · v2.7.0</span>
          <h2 className="mt-4 font-display text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">
            <SplitText text="The same Hub," />
            <br />
            <span className="text-gradient">inside your editor.</span>
          </h2>
          <p className="mt-4 max-w-lg text-ink-soft">
            Prefer clicks to keystrokes? The <strong className="text-ink">m-gpux</strong> extension brings
            30+ actions to the VS Code command palette and sidebar — no terminal required.
          </p>
          <ul className="mt-6 space-y-3">
            {EXTENSION_HIGHLIGHTS.map((h) => (
              <li key={h} className="flex items-start gap-3 text-sm text-ink-soft">
                <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-emerald-100 text-emerald-600">
                  <Check size={13} />
                </span>
                {h}
              </li>
            ))}
          </ul>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Magnet>
              <a href={MARKET} target="_blank" rel="noreferrer" className="btn-primary">
                Get the extension <ArrowRight size={16} />
              </a>
            </Magnet>
            <code className="rounded-xl border border-line bg-white/80 px-4 py-2.5 font-mono text-sm text-ink-soft shadow-soft">
              ext install m-gpux-vscode
            </code>
          </div>
        </ScrollReveal>

        <ScrollReveal delay={0.1}>
          <CommandPalette />
        </ScrollReveal>
      </div>
    </section>
  );
}
