import { useMemo, useState } from "react";
import { Check, Copy, MonitorSmartphone, Search, X } from "lucide-react";
import { ScrollReveal, SpotlightCard, SplitText } from "../reactbits";
import Icon from "../ui/Icon";
import { ALL_COMMANDS, COMMAND_GROUPS } from "../../data/commands";

const WITH_UI = ALL_COMMANDS.filter((c) => c.ext).length;

function CommandRow({ cmd, desc, ext }) {
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
      title={ext ? `Also in VS Code: ${ext}` : "Copy command"}
      className="group/row flex w-full items-start gap-3 rounded-xl border border-transparent px-3 py-2 text-left transition-colors hover:border-line hover:bg-brand-50/50"
    >
      <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${ext ? "bg-brand-400" : "bg-ink/15"}`} />
      <span className="min-w-0 flex-1">
        <code className="block break-words font-mono text-[13px] font-semibold text-ink">{cmd}</code>
        <span className="text-xs text-ink-muted">{desc}</span>
        {ext && (
          <span className="mt-1 flex items-center gap-1 font-mono text-[10px] text-brand-600">
            <MonitorSmartphone size={11} /> {ext}
          </span>
        )}
      </span>
      <span className="mt-0.5 shrink-0 text-ink-faint opacity-0 transition-opacity group-hover/row:opacity-100 group-focus-visible/row:opacity-100">
        {copied ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
      </span>
    </button>
  );
}

export default function CommandShowcase() {
  const [query, setQuery] = useState("");
  const [onlyUi, setOnlyUi] = useState(false);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    return COMMAND_GROUPS.map((g) => ({
      ...g,
      commands: g.commands.filter(
        (c) =>
          (!onlyUi || c.ext) &&
          (!q || [c.cmd, c.desc, c.ext, g.title].some((s) => s && s.toLowerCase().includes(q)))
      ),
    })).filter((g) => g.commands.length);
  }, [query, onlyUi]);

  const shown = groups.reduce((n, g) => n + g.commands.length, 0);

  return (
    <section id="commands" className="relative scroll-mt-24 py-20 sm:py-28">
      <div className="container-px">
        <div className="mx-auto max-w-2xl text-center">
          <span className="section-kicker mx-auto">
            {ALL_COMMANDS.length} commands · {COMMAND_GROUPS.length} workflows
          </span>
          <h2 className="mt-5 font-display text-4xl font-semibold tracking-[-0.025em] text-ink sm:text-5xl">
            <SplitText text="Every CLI command, mapped." />
          </h2>
          <p className="mt-4 text-ink-soft">
            Search the whole CLI, copy the exact command, and see where the VS Code extension
            gives you the same thing as a button — {WITH_UI} of {ALL_COMMANDS.length} commands do.
          </p>
        </div>

        <div className="mx-auto mt-10 flex max-w-2xl flex-col gap-3 sm:flex-row sm:items-center">
          <label className="relative flex-1">
            <Search size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-ink-faint" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search commands — pause, budget, logs, vLLM…"
              aria-label="Search commands"
              className="w-full rounded-xl border border-ink/10 bg-white/80 py-3 pl-11 pr-10 text-sm text-ink shadow-soft placeholder:text-ink-faint"
            />
            {query && (
              <button
                onClick={() => setQuery("")}
                aria-label="Clear search"
                className="absolute right-3 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-md text-ink-faint hover:text-ink"
              >
                <X size={14} />
              </button>
            )}
          </label>
          <button
            onClick={() => setOnlyUi((v) => !v)}
            aria-pressed={onlyUi}
            className={`inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border px-4 py-3 text-sm font-semibold shadow-soft transition-colors ${
              onlyUi ? "border-brand-500 bg-brand-500 text-white" : "border-ink/10 bg-white/80 text-ink-soft hover:border-brand-300"
            }`}
          >
            <MonitorSmartphone size={15} /> Has VS Code UI
          </button>
        </div>
        <p className="mt-3 text-center font-mono text-[11px] text-ink-faint" aria-live="polite">
          {shown === ALL_COMMANDS.length ? "Click any command to copy it" : `${shown} matching command${shown === 1 ? "" : "s"}`}
        </p>

        {groups.length === 0 ? (
          <p className="mt-12 text-center text-sm text-ink-muted">No command matches “{query}”.</p>
        ) : (
          <div className="mt-10 gap-5 sm:columns-2 lg:columns-3">
            {groups.map((g, i) => (
              <ScrollReveal key={g.id} delay={(i % 3) * 0.05} className="mb-5 break-inside-avoid">
                <SpotlightCard className="card p-6">
                  <div className="flex items-center gap-3">
                    <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-grad text-white shadow-soft">
                      <Icon name={g.icon} size={20} />
                    </span>
                    <h3 className="font-display text-lg font-bold text-ink">{g.title}</h3>
                    <span className="ml-auto font-mono text-[11px] text-ink-faint">{g.commands.length}</span>
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
        )}
      </div>
    </section>
  );
}
