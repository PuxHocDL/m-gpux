import { useState } from "react";
import { motion, useScroll, AnimatePresence } from "framer-motion";
import { Github, Menu, X, Terminal } from "lucide-react";
import Logo from "./Logo";
import { Magnet } from "../reactbits";

const LINKS = [
  { href: "#tutorial", label: "Tutorial" },
  { href: "#commands", label: "Commands" },
  { href: "#extension", label: "Extension" },
  { href: "#features", label: "Features" },
];

const REPO = "https://github.com/PuxHocDL/m-gpux";

export default function Navbar() {
  const { scrollYProgress } = useScroll();
  const [open, setOpen] = useState(false);

  return (
    <header className="fixed inset-x-0 top-0 z-50">
      <motion.div style={{ scaleX: scrollYProgress }} className="h-[3px] origin-left bg-brand-grad" />
      <div className="container-px pt-3">
        <nav className="flex items-center justify-between rounded-2xl border border-line/80 bg-white/70 px-4 py-2.5 shadow-soft backdrop-blur-xl">
          <Logo />

          <div className="hidden items-center gap-1 md:flex">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="rounded-lg px-3 py-2 text-sm font-medium text-ink-soft transition-colors hover:bg-brand-50 hover:text-brand-700"
              >
                {l.label}
              </a>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <a
              href={REPO}
              target="_blank"
              rel="noreferrer"
              className="hidden h-10 w-10 place-items-center rounded-xl border border-line text-ink-soft transition-colors hover:border-brand-300 hover:text-brand-700 sm:grid"
              aria-label="GitHub repository"
            >
              <Github size={18} />
            </a>
            <Magnet className="hidden sm:inline-flex">
              <a href="#tutorial" className="btn-primary">
                <Terminal size={16} /> Start tutorial
              </a>
            </Magnet>
            <button
              onClick={() => setOpen((v) => !v)}
              className="grid h-10 w-10 place-items-center rounded-xl border border-line text-ink-soft md:hidden"
              aria-label="Toggle menu"
            >
              {open ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </nav>

        <AnimatePresence>
          {open && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="mt-2 rounded-2xl border border-line bg-white/90 p-2 shadow-soft backdrop-blur-xl md:hidden"
            >
              {LINKS.map((l) => (
                <a
                  key={l.href}
                  href={l.href}
                  onClick={() => setOpen(false)}
                  className="block rounded-lg px-3 py-2.5 text-sm font-medium text-ink-soft hover:bg-brand-50 hover:text-brand-700"
                >
                  {l.label}
                </a>
              ))}
              <a href="#tutorial" onClick={() => setOpen(false)} className="btn-primary mt-1 w-full">
                <Terminal size={16} /> Start tutorial
              </a>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </header>
  );
}
