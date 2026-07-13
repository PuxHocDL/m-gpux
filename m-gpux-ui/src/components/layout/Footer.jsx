import { Github, BookText, Package } from "lucide-react";
import Logo from "./Logo";

const REPO = "https://github.com/PuxHocDL/m-gpux";
const DOCS = "https://puxhocdl.github.io/m-gpux/";
const PYPI = "https://pypi.org/project/m-gpux/";

export default function Footer() {
  return (
    <footer className="relative mt-24 border-t border-line bg-white/60 backdrop-blur-xl">
      <div className="container-px grid grid-cols-2 gap-8 py-14 md:grid-cols-4">
        <div className="col-span-2">
          <Logo />
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-ink-muted">
            A professional, interactive hub and CLI for scaling AI workloads on Modal GPUs —
            profiles, GPU sessions, hosting, serving and cost visibility, all in one tool.
          </p>
          <div className="mt-5 flex items-center gap-2">
            <a href={REPO} target="_blank" rel="noreferrer" className="btn-ghost px-3 py-2 text-xs">
              <Github size={15} /> GitHub
            </a>
            <a href={PYPI} target="_blank" rel="noreferrer" className="btn-ghost px-3 py-2 text-xs">
              <Package size={15} /> PyPI
            </a>
          </div>
        </div>

        <div>
          <h4 className="mb-4 font-display text-sm font-bold text-ink">Resources</h4>
          <ul className="space-y-3 text-sm text-ink-muted">
            <li><a href={DOCS} className="transition-colors hover:text-brand-700" target="_blank" rel="noreferrer">Documentation</a></li>
            <li><a href={`${DOCS}getting-started/`} className="transition-colors hover:text-brand-700" target="_blank" rel="noreferrer">Getting started</a></li>
            <li><a href={`${DOCS}commands/`} className="transition-colors hover:text-brand-700" target="_blank" rel="noreferrer">Command reference</a></li>
          </ul>
        </div>

        <div>
          <h4 className="mb-4 font-display text-sm font-bold text-ink">Community</h4>
          <ul className="space-y-3 text-sm text-ink-muted">
            <li><a href={REPO} className="transition-colors hover:text-brand-700" target="_blank" rel="noreferrer">GitHub repository</a></li>
            <li><a href={`${REPO}/issues`} className="transition-colors hover:text-brand-700" target="_blank" rel="noreferrer">Report an issue</a></li>
            <li><a href={`${REPO}/blob/main/LICENSE`} className="transition-colors hover:text-brand-700" target="_blank" rel="noreferrer">MIT License</a></li>
          </ul>
        </div>
      </div>

      <div className="container-px flex flex-col items-center justify-between gap-2 border-t border-line py-6 text-center text-xs text-ink-faint sm:flex-row">
        <p className="inline-flex items-center gap-1.5">
          <BookText size={14} /> © 2026 m-gpux · MIT Licensed · Made by Pux.
        </p>
        <p>Built with React, Tailwind & React-Bits-style motion.</p>
      </div>
    </footer>
  );
}
