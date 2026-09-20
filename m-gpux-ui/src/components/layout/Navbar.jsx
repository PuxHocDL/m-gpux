import { useState } from "react";
import { motion, useScroll, AnimatePresence } from "framer-motion";
import { Github, Menu, X, ArrowUpRight } from "lucide-react";
import Logo from "./Logo";
import { Magnet } from "../reactbits";

const LINKS = [
  { href: "/#features", label: "Product" },
  { href: "/#tutorial", label: "Tour" },
  { href: "/docs/", label: "Docs" },
  { href: "/#commands", label: "CLI" },
  { href: "/#extension", label: "Extension" },
];

const REPO = "https://github.com/PuxHocDL/m-gpux";

export default function Navbar() {
  const { scrollYProgress } = useScroll();
  const [open, setOpen] = useState(false);

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-ink/10 bg-cream-50/92 backdrop-blur-xl">
      <motion.div style={{ scaleX: scrollYProgress }} className="h-[3px] origin-left bg-brand-grad" />
      <div className="container-px">
        <nav className="flex h-[68px] items-center justify-between">
          <Logo />

          <div className="hidden items-center gap-1 md:flex">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="rounded-lg px-3 py-2 text-[13px] font-medium text-ink-muted transition-colors hover:bg-brand-50 hover:text-brand-700"
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
              className="hidden h-10 w-10 place-items-center rounded-xl border border-ink/10 bg-white/70 text-ink-soft transition-colors hover:border-brand-300 hover:text-brand-700 sm:grid"
              aria-label="GitHub repository"
            >
              <Github size={18} />
            </a>
            <Magnet className="hidden sm:inline-flex">
              <a href="/#get-started" className="btn-primary py-2.5">
                Get v3 <ArrowUpRight size={16} />
              </a>
            </Magnet>
            <button
              onClick={() => setOpen((v) => !v)}
              className="grid h-10 w-10 place-items-center rounded-xl border border-ink/10 bg-white/70 text-ink-soft md:hidden"
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
              className="absolute inset-x-5 top-[72px] rounded-2xl border border-ink/10 bg-cream-50/95 p-2 shadow-card backdrop-blur-xl md:hidden"
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
              <a href="/#get-started" onClick={() => setOpen(false)} className="btn-primary mt-1 w-full">
                Get v3 <ArrowUpRight size={16} />
              </a>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </header>
  );
}
