import { useState } from "react";
import { Copy, Check } from "lucide-react";

/** CopyChip — a monospace command pill with a copy-to-clipboard button. */
export default function CopyChip({ text, prefix = "$", className = "", dark = false }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <button
      onClick={copy}
      className={`group inline-flex items-center gap-3 rounded-xl border px-4 py-2.5 font-mono text-sm shadow-soft transition-colors ${
        dark
          ? "border-white/15 bg-white/[0.06] hover:border-brand-400/70"
          : "border-line bg-white/80 hover:border-brand-300"
      } ${className}`}
    >
      <span className="text-brand-400">{prefix}</span>
      <span className={dark ? "text-white/85" : "text-ink-soft"}>{text}</span>
      <span className={`ml-1 transition-colors ${dark ? "text-white/35 group-hover:text-brand-300" : "text-ink-faint group-hover:text-brand-600"}`}>
        {copied ? <Check size={15} className="text-emerald-500" /> : <Copy size={15} />}
      </span>
    </button>
  );
}
