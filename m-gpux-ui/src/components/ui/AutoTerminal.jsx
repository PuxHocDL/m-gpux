import { useEffect, useRef, useState } from "react";
import { TerminalChrome, TerminalLine } from "./Terminal";

/**
 * AutoTerminal — types a looping script of commands + output on its own, to
 * preview the real `m-gpux` CLI feel. Honours prefers-reduced-motion (renders a
 * single static frame instead of animating).
 */
export default function AutoTerminal({ script, title = "bash — m-gpux", className = "" }) {
  const [history, setHistory] = useState([]);
  const [typed, setTyped] = useState("");
  const [prompt, setPrompt] = useState("~");
  const scrollRef = useRef(null);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      const first = script[0];
      setHistory([{ tone: "command", prompt: first.prompt || "~", text: first.cmd }, ...first.output]);
      return;
    }

    let cancelled = false;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

    async function run() {
      while (!cancelled) {
        for (const item of script) {
          if (cancelled) return;
          setTyped("");
          setPrompt(item.prompt || "~");
          for (let i = 0; i < item.cmd.length; i++) {
            if (cancelled) return;
            setTyped(item.cmd.slice(0, i + 1));
            await sleep(28 + Math.random() * 46);
          }
          await sleep(260);
          if (cancelled) return;
          setHistory((h) => [...h, { tone: "command", prompt: item.prompt || "~", text: item.cmd }]);
          setTyped("");
          for (const line of item.output) {
            if (cancelled) return;
            await sleep(150);
            setHistory((h) => [...h, line]);
          }
          await sleep(item.pause ?? 1700);
          if (cancelled) return;
          setHistory([]);
        }
      }
    }
    run();
    return () => {
      cancelled = true;
    };
  }, [script]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [history, typed]);

  return (
    <TerminalChrome title={title} className={className}>
      <div ref={scrollRef} className="h-[300px] space-y-1.5 overflow-hidden p-5">
        {history.map((line, i) => (
          <TerminalLine key={i} line={line} />
        ))}
        {typed !== "" && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-emerald-400">➜</span>
            <span className="text-brand-300">{prompt}</span>
            <span className="text-term-text">{typed}</span>
            <span className="inline-block h-4 w-2 animate-blink bg-brand-300" />
          </div>
        )}
      </div>
    </TerminalChrome>
  );
}
