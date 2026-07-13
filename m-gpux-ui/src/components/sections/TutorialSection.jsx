import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Check,
  Lock,
  Lightbulb,
  Wand2,
  CornerDownLeft,
  RotateCcw,
  Trophy,
  Terminal as TerminalIcon,
  ChevronRight,
} from "lucide-react";
import { TerminalChrome, TerminalLine } from "../ui/Terminal";
import { SplitText, ScrollReveal } from "../reactbits";
import { TUTORIAL_STEPS } from "../../data/tutorial";

const TOTAL = TUTORIAL_STEPS.length;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const normalize = (s) => s.trim().replace(/\s+/g, " ");

const INTRO = [
  { tone: "dim", text: "# m-gpux interactive tour — type each command, press Enter to advance." },
  { tone: "dim", text: "# stuck? tap Hint, or Auto-type to fill the command for you." },
];

export default function TutorialSection() {
  const reduce = useMemo(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  );

  const [current, setCurrent] = useState(0);
  const [completed, setCompleted] = useState([]);
  const [history, setHistory] = useState(INTRO);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(false);
  const [shake, setShake] = useState(false);
  const [attempts, setAttempts] = useState(0);
  const [showHint, setShowHint] = useState(false);
  const [finished, setFinished] = useState(false);
  const [cmdHistory, setCmdHistory] = useState([]);

  const inputRef = useRef(null);
  const scrollRef = useRef(null);
  const termRef = useRef(null);
  const runningRef = useRef(false);
  const typingRef = useRef(false);
  const mountedRef = useRef(true);

  const step = TUTORIAL_STEPS[current];
  const doneCount = completed.length;
  const progress = Math.round((doneCount / TOTAL) * 100);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Reset per-step ephemeral UI and focus the prompt.
  useEffect(() => {
    setError(false);
    setShowHint(false);
    setAttempts(0);
    if (!reduce) inputRef.current?.focus();
  }, [current, reduce]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [history, input, running]);

  const fireSpark = () => {
    const el = termRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    window.dispatchEvent(
      new CustomEvent("mgpux:spark", {
        detail: { x: r.left + r.width / 2, y: r.top + 60, count: 22 },
      })
    );
  };

  const celebrate = () => {
    const el = termRef.current;
    const r = el?.getBoundingClientRect();
    window.dispatchEvent(
      new CustomEvent("mgpux:spark", {
        detail: {
          x: r ? r.left + r.width / 2 : window.innerWidth / 2,
          y: r ? r.top + r.height / 2 : window.innerHeight / 2,
          count: 60,
        },
      })
    );
  };

  const autoType = async () => {
    if (runningRef.current || typingRef.current) return;
    typingRef.current = true;
    setError(false);
    setInput("");
    if (reduce) {
      setInput(step.command);
      typingRef.current = false;
      inputRef.current?.focus();
      return;
    }
    for (let i = 0; i < step.command.length; i++) {
      if (!mountedRef.current) return;
      setInput(step.command.slice(0, i + 1));
      await sleep(24 + Math.random() * 42);
    }
    typingRef.current = false;
    inputRef.current?.focus();
  };

  const submit = async () => {
    if (runningRef.current || typingRef.current) return;
    const norm = normalize(input);
    if (!norm) return;

    if (!step.validate.test(norm)) {
      setError(true);
      setShake(true);
      setAttempts((a) => a + 1);
      setTimeout(() => mountedRef.current && setShake(false), 480);
      if (attempts + 1 >= 2) setShowHint(true);
      return;
    }

    // Correct ✔
    setError(false);
    runningRef.current = true;
    setRunning(true);
    setHistory((h) => [...h, { tone: "command", prompt: step.prompt, text: input.trim() }]);
    setCmdHistory((h) => [...h, input.trim()]);
    setInput("");

    for (const line of step.output) {
      await sleep(reduce ? 0 : 130);
      if (!mountedRef.current) return;
      setHistory((h) => [...h, line]);
    }
    await sleep(reduce ? 0 : 220);
    if (!mountedRef.current) return;

    setCompleted((c) => (c.includes(current) ? c : [...c, current]));
    fireSpark();
    runningRef.current = false;
    setRunning(false);

    if (current + 1 < TOTAL) {
      await sleep(reduce ? 0 : 360);
      if (mountedRef.current) setCurrent(current + 1);
    } else {
      setFinished(true);
      celebrate();
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submit();
    } else if (e.key === "ArrowUp" && cmdHistory.length) {
      e.preventDefault();
      setInput(cmdHistory[cmdHistory.length - 1]);
    }
  };

  const restart = () => {
    setCurrent(0);
    setCompleted([]);
    setHistory(INTRO);
    setInput("");
    setError(false);
    setShowHint(false);
    setFinished(false);
    setCmdHistory([]);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  return (
    <section id="tutorial" className="relative scroll-mt-24 py-20 sm:py-28">
      <div className="container-px">
        {/* Header */}
        <div className="mx-auto max-w-2xl text-center">
          <span className="pill mx-auto"><TerminalIcon size={13} /> Interactive tutorial</span>
          <h2 className="mt-4 font-display text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">
            <SplitText text="Learn m-gpux by doing." />
          </h2>
          <p className="mt-4 text-ink-soft">
            A real terminal, real commands. Type each one to clear the step — exactly how you'd drive
            the CLI on your own machine.
          </p>
        </div>

        {/* Progress */}
        <ScrollReveal className="mx-auto mt-8 max-w-3xl">
          <div className="card flex items-center gap-4 px-5 py-3.5">
            <span className="font-mono text-sm font-semibold text-brand-600">
              {doneCount}/{TOTAL}
            </span>
            <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-brand-100">
              <motion.div
                className="absolute inset-y-0 left-0 rounded-full bg-brand-grad"
                animate={{ width: `${progress}%` }}
                transition={{ type: "spring", stiffness: 120, damping: 20 }}
              />
            </div>
            <span className="hidden items-center gap-1.5 text-sm font-semibold text-ink-soft sm:inline-flex">
              <Trophy size={15} className="text-brand-500" /> {doneCount * 120} XP
            </span>
            <button
              onClick={restart}
              className="grid h-9 w-9 place-items-center rounded-lg border border-line text-ink-muted transition-colors hover:border-brand-300 hover:text-brand-600"
              title="Restart tour"
            >
              <RotateCcw size={15} />
            </button>
          </div>
        </ScrollReveal>

        {/* Body */}
        <div className="mt-10 grid gap-6 lg:grid-cols-[minmax(0,1fr)_1.35fr]">
          {/* Stepper */}
          <ol className="space-y-2.5">
            {TUTORIAL_STEPS.map((s, i) => {
              const isDone = completed.includes(i);
              const isActive = i === current;
              const isLocked = i > current && !isDone;
              return (
                <li key={s.id}>
                  <div
                    className={`flex items-start gap-3 rounded-2xl border px-4 py-3 transition-all ${
                      isActive
                        ? "border-brand-300 bg-white shadow-soft ring-2 ring-brand-200/60"
                        : isDone
                        ? "border-emerald-200 bg-emerald-50/50"
                        : "border-line bg-white/50"
                    }`}
                  >
                    <span
                      className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-bold ${
                        isDone
                          ? "bg-emerald-500 text-white"
                          : isActive
                          ? "bg-brand-grad text-white"
                          : "bg-brand-100 text-brand-400"
                      }`}
                    >
                      {isDone ? <Check size={15} /> : isLocked ? <Lock size={13} /> : i + 1}
                    </span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className={`truncate text-sm font-semibold ${isLocked ? "text-ink-faint" : "text-ink"}`}>
                          {s.title}
                        </p>
                        <span className="hidden rounded-full bg-brand-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand-500 sm:inline">
                          {s.chip}
                        </span>
                      </div>
                      {isActive && !isDone && (
                        <p className="mt-1 line-clamp-2 text-xs text-ink-muted">{s.goal}</p>
                      )}
                      {isDone && (
                        <p className="mt-0.5 inline-flex items-center gap-1 text-xs font-medium text-emerald-600">
                          <Check size={12} /> {s.reward}
                        </p>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>

          {/* Terminal + mission */}
          <div ref={termRef} className="lg:sticky lg:top-24">
            {/* Mission card */}
            <div className="card mb-4 p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-brand-500">
                    Step {current + 1} · {step.chip}
                  </p>
                  <h3 className="mt-1 font-display text-lg font-bold text-ink">{step.title}</h3>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    onClick={() => setShowHint((v) => !v)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-2 text-xs font-semibold text-ink-soft transition-colors hover:border-brand-300 hover:text-brand-600"
                  >
                    <Lightbulb size={14} /> Hint
                  </button>
                  <button
                    onClick={autoType}
                    disabled={running}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-xs font-semibold text-brand-600 transition-colors hover:bg-brand-100 disabled:opacity-50"
                  >
                    <Wand2 size={14} /> Auto-type
                  </button>
                </div>
              </div>
              <p className="mt-2.5 text-sm leading-relaxed text-ink-soft">{step.goal}</p>
              <AnimatePresence>
                {showHint && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <p className="mt-3 inline-flex items-start gap-2 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700">
                      <Lightbulb size={14} className="mt-0.5 shrink-0" /> {step.hint}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Terminal */}
            <motion.div animate={shake ? { x: [0, -9, 9, -6, 6, 0] } : {}} transition={{ duration: 0.45 }}>
              <TerminalChrome
                title="bash — m-gpux tour"
                rightSlot={
                  <span className="font-mono text-[11px] text-term-dim">
                    {finished ? "tour complete" : `step ${current + 1}/${TOTAL}`}
                  </span>
                }
              >
                <div ref={scrollRef} className="h-[330px] space-y-1.5 overflow-y-auto p-5">
                  {history.map((line, i) => (
                    <TerminalLine key={i} line={line} />
                  ))}

                  {running && <div className="text-term-dim">…</div>}

                  {!finished && !running && (
                    <div className="flex items-center gap-2 pt-1">
                      <span className="text-emerald-400">➜</span>
                      <span className="text-brand-300">{step.prompt}</span>
                      <input
                        ref={inputRef}
                        value={input}
                        onChange={(e) => {
                          setInput(e.target.value);
                          if (error) setError(false);
                        }}
                        onKeyDown={onKeyDown}
                        spellCheck={false}
                        autoComplete="off"
                        autoCapitalize="off"
                        placeholder="type the command…"
                        className="flex-1 bg-transparent font-mono text-[13px] text-term-text caret-brand-300 placeholder:text-term-dim/60 focus:outline-none"
                      />
                      <button
                        onClick={submit}
                        className="inline-flex items-center gap-1 rounded-md border border-term-line px-2 py-1 font-mono text-[11px] text-brand-300 transition-colors hover:bg-term-panel"
                      >
                        Run <CornerDownLeft size={12} />
                      </button>
                    </div>
                  )}

                  {finished && (
                    <div className="flex items-center gap-2 pt-1 text-brand-300">
                      <Trophy size={14} /> all steps cleared — well played!
                    </div>
                  )}
                </div>
              </TerminalChrome>
            </motion.div>

            {/* Inline error */}
            <AnimatePresence>
              {error && (
                <motion.p
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="mt-3 inline-flex items-center gap-2 rounded-xl bg-red-50 px-3 py-2 text-xs font-medium text-red-600"
                >
                  Not quite — that isn't the command this step expects.{" "}
                  <button onClick={() => setShowHint(true)} className="underline underline-offset-2">
                    show hint
                  </button>
                </motion.p>
              )}
            </AnimatePresence>

            {/* Finish banner */}
            <AnimatePresence>
              {finished && (
                <motion.div
                  initial={{ opacity: 0, y: 12, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  className="mt-4 flex flex-col items-center justify-between gap-3 rounded-2xl border border-brand-200 bg-brand-grad p-5 text-white shadow-glow sm:flex-row"
                >
                  <div className="flex items-center gap-3">
                    <span className="grid h-11 w-11 place-items-center rounded-xl bg-white/20">
                      <Trophy size={22} />
                    </span>
                    <div>
                      <p className="font-display text-lg font-extrabold">Tour complete · {TOTAL * 120} XP</p>
                      <p className="text-sm text-white/85">You ran the full m-gpux loop. Time for the real thing.</p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <a
                      href="#commands"
                      className="inline-flex items-center gap-1.5 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-brand-700 transition-transform hover:scale-[1.03]"
                    >
                      Explore commands <ChevronRight size={15} />
                    </a>
                    <button
                      onClick={restart}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-white/15 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-white/25"
                    >
                      <RotateCcw size={15} /> Replay
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </section>
  );
}
