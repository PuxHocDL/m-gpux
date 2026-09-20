import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Blocks,
  Box,
  Check,
  CheckCircle2,
  ChevronDown,
  Clipboard,
  Command,
  Globe2,
  History,
  Layers3,
  Rocket,
  Search,
  Server,
  Users,
  WalletCards,
} from "lucide-react";
import { DOC_REQUIREMENTS, DOC_TOPICS } from "../../data/docs";

const ICONS = { Blocks, Box, Globe2, History, Layers3, Rocket, Server, Users, WalletCards };
const FULL_DOCS = "https://puxhocdl.github.io/m-gpux/";
const GROUPS = [
  { label: "Start here", ids: ["quickstart", "profiles"] },
  { label: "Build & deploy", ids: ["devboxes", "compose", "hosting", "serving"] },
  { label: "Integrations", ids: ["extension"] },
  { label: "Operations", ids: ["costs", "sessions"] },
];

function initialTopic() {
  if (typeof window === "undefined") return DOC_TOPICS[0].id;
  const id = window.location.hash.slice(1);
  return DOC_TOPICS.some((topic) => topic.id === id) ? id : DOC_TOPICS[0].id;
}

function CodeBlock({ code }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div className="group relative mt-5 overflow-hidden rounded-lg border border-brand-900/15 bg-term-bg shadow-soft">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2 font-mono text-[9px] uppercase tracking-[0.16em] text-white/40">
        <span>terminal</span>
        <button onClick={copy} className="inline-flex items-center gap-1.5 text-white/45 transition-colors hover:text-white" aria-label="Copy command">
          {copied ? <Check size={12} className="text-brand-300" /> : <Clipboard size={12} />}
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 font-mono text-[12px] leading-7 text-term-text sm:text-[13px]">
        {code.split("\n").map((line, index) => (
          <span key={`${line}-${index}`} className="block"><span className="mr-3 select-none text-brand-300">$</span>{line}</span>
        ))}
      </pre>
    </div>
  );
}

function TopicButton({ topic, selected, onSelect }) {
  const TopicIcon = ICONS[topic.icon];
  return (
    <button
      onClick={() => onSelect(topic.id)}
      className={`group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors ${
        selected ? "bg-brand-700 font-semibold text-white shadow-soft" : "text-ink-muted hover:bg-brand-50 hover:text-brand-800"
      }`}
    >
      <TopicIcon size={14} className={selected ? "text-brand-200" : "text-ink-faint group-hover:text-brand-600"} />
      <span className="truncate">{topic.label}</span>
    </button>
  );
}

export default function DocsSection() {
  const [activeId, setActiveId] = useState(initialTopic);
  const [query, setQuery] = useState("");
  const searchRef = useRef(null);
  const activeIndex = DOC_TOPICS.findIndex((topic) => topic.id === activeId);
  const active = DOC_TOPICS[activeIndex] || DOC_TOPICS[0];
  const previous = activeIndex > 0 ? DOC_TOPICS[activeIndex - 1] : null;
  const next = activeIndex < DOC_TOPICS.length - 1 ? DOC_TOPICS[activeIndex + 1] : null;

  const filteredIds = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return new Set(DOC_TOPICS.map((topic) => topic.id));
    return new Set(
      DOC_TOPICS.filter((topic) =>
        [topic.label, topic.title, topic.summary, ...topic.sections.flatMap((section) => [section.title, section.body, section.code || ""])]
          .join(" ")
          .toLowerCase()
          .includes(needle)
      ).map((topic) => topic.id)
    );
  }, [query]);

  useEffect(() => {
    const syncHash = () => {
      const id = window.location.hash.slice(1);
      if (DOC_TOPICS.some((topic) => topic.id === id)) setActiveId(id);
    };
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  useEffect(() => {
    const focusSearch = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  const selectTopic = (id) => {
    setActiveId(id);
    setQuery("");
    window.history.replaceState(null, "", `#${id}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <section id="docs" className="min-h-screen bg-cream-50">
      <div className="sticky top-[68px] z-40 border-b border-brand-900/30 bg-brand-800 text-white shadow-soft">
        <div className="container-px flex min-h-14 items-center gap-4 py-2">
          <a href="/docs/" className="flex items-center gap-2 text-sm font-semibold text-white">
            <span className="text-white/55">m-gpux</span>
            <span className="text-white/35">/</span>
            <span>Docs</span>
          </a>
          <span className="hidden rounded-md border border-white/15 bg-white/10 px-2 py-1 font-mono text-[9px] text-white/70 sm:inline">v3.0</span>

          <label className="ml-auto flex w-full max-w-sm items-center gap-2 rounded-lg border border-ink/10 bg-white px-3 py-2 text-sm shadow-soft focus-within:border-brand-300">
            <Search size={14} className="shrink-0 text-ink-faint" />
            <input
              ref={searchRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search documentation..."
              className="min-w-0 flex-1 bg-transparent text-[13px] text-ink placeholder:text-ink-faint focus:outline-none focus:ring-0"
            />
            <span className="hidden items-center gap-1 rounded border border-ink/10 bg-cream-100 px-1.5 py-0.5 font-mono text-[9px] text-ink-faint sm:inline-flex">
              <Command size={9} /> K
            </span>
          </label>
          <a href={FULL_DOCS} target="_blank" rel="noreferrer" className="hidden items-center gap-1.5 text-xs font-semibold text-white/65 hover:text-white md:inline-flex">
            Reference <ArrowUpRight size={13} />
          </a>
        </div>
      </div>

      <div className="container-px grid lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-10 xl:grid-cols-[230px_minmax(0,790px)_210px] xl:gap-12">
        <aside className="hidden border-r border-ink/10 py-10 pr-5 lg:block">
          <div className="sticky top-[150px] max-h-[calc(100vh-170px)] overflow-y-auto pr-1">
            {GROUPS.map((group) => {
              const topics = group.ids.map((id) => DOC_TOPICS.find((topic) => topic.id === id)).filter((topic) => topic && filteredIds.has(topic.id));
              if (!topics.length) return null;
              return (
                <div key={group.label} className="mb-7">
                  <p className="mb-2 px-2.5 font-mono text-[9px] font-semibold uppercase tracking-[0.16em] text-ink-faint">{group.label}</p>
                  <nav className="space-y-0.5" aria-label={group.label}>
                    {topics.map((topic) => <TopicButton key={topic.id} topic={topic} selected={topic.id === active.id} onSelect={selectTopic} />)}
                  </nav>
                </div>
              );
            })}
            {!filteredIds.size && <p className="px-2.5 text-xs leading-relaxed text-ink-muted">No documentation matches “{query}”.</p>}
          </div>
        </aside>

        <article className="min-w-0 py-10 sm:py-14 lg:py-16" aria-live="polite">
          <details className="mb-8 rounded-lg border border-ink/10 bg-white p-3 lg:hidden">
            <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-semibold text-ink">
              {active.label} <ChevronDown size={15} />
            </summary>
            <div className="mt-3 grid gap-1 border-t border-ink/10 pt-3 sm:grid-cols-2">
              {DOC_TOPICS.filter((topic) => filteredIds.has(topic.id)).map((topic) => (
                <TopicButton key={topic.id} topic={topic} selected={topic.id === active.id} onSelect={selectTopic} />
              ))}
            </div>
          </details>

          <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">
            <a href="/docs/" className="hover:text-brand-700">Documentation</a>
            <span>/</span>
            <span className="text-brand-700">{active.label}</span>
          </div>
          <h1 className="mt-5 max-w-3xl font-display text-5xl font-semibold leading-[1.04] tracking-[-0.02em] text-ink sm:text-6xl">{active.title}</h1>
          <p className="mt-6 max-w-3xl text-base leading-8 text-ink-muted sm:text-lg">{active.summary}</p>
          <div className="mt-5 flex items-center gap-3 text-xs text-ink-faint">
            <span>{active.time} read</span><span>·</span><span>Updated for v3.0</span>
          </div>

          <div className="mt-10 border-t border-ink/10 pt-10">
            <div className="space-y-14">
              {active.sections.map((section, index) => {
                const sectionId = `${active.id}-${index + 1}`;
                return (
                  <section key={section.title} id={sectionId} className="scroll-mt-40">
                    <h2 className="font-sans text-xl font-bold tracking-[-0.02em] text-ink sm:text-2xl">{section.title}</h2>
                    <p className="mt-4 text-[15px] leading-8 text-ink-muted">{section.body}</p>
                    {section.steps && (
                      <ol className="mt-6 space-y-3">
                        {section.steps.map((step) => (
                          <li key={step} className="flex items-start gap-3 text-sm leading-6 text-ink-soft">
                            <CheckCircle2 size={16} className="mt-1 shrink-0 text-brand-500" /> {step}
                          </li>
                        ))}
                      </ol>
                    )}
                    {section.code && <CodeBlock code={section.code} />}
                  </section>
                );
              })}
            </div>

            <div className="mt-14 border-l-2 border-brand-500 bg-brand-50/70 px-5 py-4 text-sm leading-7 text-brand-900">
              <strong className="mr-2">Good to know.</strong>{active.tip}
            </div>

            <nav className="mt-16 grid gap-4 border-t border-ink/10 pt-8 sm:grid-cols-2" aria-label="Documentation pagination">
              {previous ? (
                <button onClick={() => selectTopic(previous.id)} className="group rounded-lg border border-ink/10 bg-white p-4 text-left transition-colors hover:border-brand-300">
                  <span className="flex items-center gap-1.5 text-xs text-ink-faint"><ArrowLeft size={13} /> Previous</span>
                  <span className="mt-2 block text-sm font-semibold text-ink group-hover:text-brand-700">{previous.label}</span>
                </button>
              ) : <span />}
              {next && (
                <button onClick={() => selectTopic(next.id)} className="group rounded-lg border border-ink/10 bg-white p-4 text-right transition-colors hover:border-brand-300">
                  <span className="flex items-center justify-end gap-1.5 text-xs text-ink-faint">Next <ArrowRight size={13} /></span>
                  <span className="mt-2 block text-sm font-semibold text-ink group-hover:text-brand-700">{next.label}</span>
                </button>
              )}
            </nav>
          </div>
        </article>

        <aside className="hidden py-16 xl:block">
          <div className="sticky top-[150px]">
            <p className="font-mono text-[9px] font-semibold uppercase tracking-[0.16em] text-ink-faint">On this page</p>
            <nav className="mt-4 space-y-3 border-l border-ink/10 pl-4">
              {active.sections.map((section, index) => (
                <a key={section.title} href={`#${active.id}-${index + 1}`} className="block text-xs leading-relaxed text-ink-muted transition-colors hover:text-brand-700">
                  {section.title}
                </a>
              ))}
            </nav>

            <div className="mt-9 border-t border-ink/10 pt-7">
              <p className="font-mono text-[9px] font-semibold uppercase tracking-[0.16em] text-ink-faint">Requirements</p>
              <ul className="mt-4 space-y-3">
                {DOC_REQUIREMENTS.map((requirement) => (
                  <li key={requirement} className="flex items-start gap-2 text-xs leading-relaxed text-ink-muted">
                    <Check size={12} className="mt-0.5 shrink-0 text-brand-600" /> {requirement}
                  </li>
                ))}
              </ul>
            </div>

            <a href="https://github.com/PuxHocDL/m-gpux/issues" target="_blank" rel="noreferrer" className="mt-9 inline-flex items-center gap-1.5 border-t border-ink/10 pt-7 text-xs font-medium text-ink-muted hover:text-brand-700">
              Found a docs issue? <ArrowUpRight size={12} />
            </a>
          </div>
        </aside>
      </div>

      <div className="border-t border-ink/10 py-6 text-center text-xs text-ink-faint">
        m-gpux v3 documentation · CLI and VS Code extension
      </div>
    </section>
  );
}
