import React from 'react';
import { ArrowRight } from 'lucide-react';
import { motion } from 'framer-motion';
import TerminalMockup from './TerminalMockup';

export default function Hero() {
  return (
    <section className="pt-32 pb-20 px-6">
      <div className="max-w-4xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <h1 className="text-5xl md:text-7xl font-bold tracking-tight mb-6 bg-gradient-to-br from-foreground to-muted bg-clip-text text-transparent">
            The API to spin up GPUs and deploy AI at scale.
          </h1>
          <p className="text-lg md:text-xl text-muted mb-10 max-w-2xl mx-auto">
            A professional CLI toolkit for Modal power users. Need fast GPU access, multi-profile account control, and simple cost visibility? Look no further.
          </p>
          <div className="flex items-center justify-center gap-4">
            <button className="bg-primary text-white px-6 py-3 rounded-md font-semibold hover:bg-orange-600 transition-colors flex items-center gap-2 shadow-lg shadow-orange-500/20">
              Start building <ArrowRight className="w-4 h-4" />
            </button>
            <button className="bg-surface border border-border px-6 py-3 rounded-md font-semibold hover:bg-border transition-colors">
              View Docs
            </button>
          </div>
        </motion.div>

        <TerminalMockup />
      </div>
    </section>
  );
}
