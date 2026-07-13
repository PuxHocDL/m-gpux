// Shared terminal chrome + line rendering used by the Hero demo and the tutorial.

export const TONE = {
  prompt: "text-brand-300",
  command: "text-term-text",
  ok: "text-emerald-400",
  warn: "text-amber-300",
  info: "text-sky-300",
  accent: "text-brand-300",
  url: "text-sky-300 underline decoration-dotted underline-offset-2",
  dim: "text-term-dim",
  text: "text-term-text",
};

export function TerminalChrome({ title = "bash — m-gpux", children, className = "", rightSlot }) {
  return (
    <div className={`overflow-hidden rounded-2xl border border-term-line bg-term-bg shadow-term ${className}`}>
      <div className="flex items-center gap-2 border-b border-term-line bg-term-panel px-4 py-3">
        <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
        <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
        <span className="h-3 w-3 rounded-full bg-[#28c840]" />
        <span className="ml-3 font-mono text-xs text-term-dim">{title}</span>
        {rightSlot ? <div className="ml-auto">{rightSlot}</div> : null}
      </div>
      <div className="font-mono text-[13px] leading-relaxed">{children}</div>
    </div>
  );
}

/** A single rendered output line. `command` lines get the ➜ prompt prefix. */
export function TerminalLine({ line }) {
  if (line.tone === "command") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-emerald-400">➜</span>
        <span className="text-brand-300">{line.prompt || "~"}</span>
        <span className="text-term-text">{line.text}</span>
      </div>
    );
  }
  return (
    <div className={TONE[line.tone] || TONE.text}>
      {line.text}
      {line.suffix ? <span className="text-term-text"> {line.suffix}</span> : null}
    </div>
  );
}
