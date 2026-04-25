import React from 'react';
import { Terminal } from 'lucide-react';

export default function Footer() {
  return (
    <footer className="border-t border-border bg-surface/30 pt-16 pb-8 px-6">
      <div className="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
        <div className="col-span-2">
          <div className="flex items-center gap-2 mb-4">
            <Terminal className="text-primary w-5 h-5" />
            <span className="font-bold text-lg">m-gpux</span>
          </div>
          <p className="text-muted text-sm max-w-sm mb-6">
            The professional CLI toolkit for Modal power users. Built for speed, cost visibility, and seamless multi-account management.
          </p>
        </div>
        <div>
          <h4 className="font-bold mb-4">Resources</h4>
          <ul className="space-y-3 text-sm text-muted">
            <li><a href="#" className="hover:text-foreground transition-colors">Documentation</a></li>
            <li><a href="#" className="hover:text-foreground transition-colors">Getting Started</a></li>
            <li><a href="#" className="hover:text-foreground transition-colors">Command Reference</a></li>
          </ul>
        </div>
        <div>
          <h4 className="font-bold mb-4">Community</h4>
          <ul className="space-y-3 text-sm text-muted">
            <li><a href="#" className="hover:text-foreground transition-colors">GitHub Repository</a></li>
            <li><a href="#" className="hover:text-foreground transition-colors">Report an Issue</a></li>
            <li><a href="#" className="hover:text-foreground transition-colors">License</a></li>
          </ul>
        </div>
      </div>
      <div className="max-w-7xl mx-auto pt-8 border-t border-border text-center text-sm text-muted">
        <p>© 2026 m-gpux open-source project. Released under the MIT License.</p>
      </div>
    </footer>
  );
}
