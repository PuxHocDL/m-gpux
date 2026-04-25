import React from 'react';
import { Database, Play, Code2, Layers, Cpu, CreditCard } from 'lucide-react';

export default function FeaturesGrid() {
  const features = [
    {
      title: "LLM API Server",
      desc: "Deploy any HuggingFace model as an OpenAI-compatible endpoint with API key auth.",
      icon: <Cpu className="w-6 h-6 text-primary" />,
      colSpan: "md:col-span-2"
    },
    {
      title: "Interactive Hub",
      desc: "Spin up Jupyter, execute scripts, and establish web shell sessions instantly.",
      icon: <Play className="w-6 h-6 text-blue-500" />,
      colSpan: "md:col-span-1"
    },
    {
      title: "Vision Workflows",
      desc: "Train and predict image classification models directly from local datasets.",
      icon: <Code2 className="w-6 h-6 text-green-500" />,
      colSpan: "md:col-span-1"
    },
    {
      title: "Cost Visibility",
      desc: "Inspect billing per profile or aggregate compute spend across all configured accounts.",
      icon: <CreditCard className="w-6 h-6 text-yellow-500" />,
      colSpan: "md:col-span-2"
    }
  ];

  return (
    <section className="py-24 px-6 relative">
      <div className="max-w-5xl mx-auto">
        <div className="mb-16">
          <h2 className="text-3xl md:text-5xl font-bold mb-4">Transform GPU workflows into simple commands</h2>
          <p className="text-muted text-lg max-w-2xl">m-gpux abstracts away infrastructure so you can focus on building AI.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {features.map((feature, i) => (
            <div 
              key={i} 
              className={`bg-surface border border-border rounded-2xl p-8 hover:border-primary/50 transition-colors group ${feature.colSpan}`}
            >
              <div className="bg-background w-12 h-12 rounded-lg flex items-center justify-center mb-6 group-hover:scale-110 transition-transform border border-border">
                {feature.icon}
              </div>
              <h3 className="text-xl font-bold mb-3">{feature.title}</h3>
              <p className="text-muted leading-relaxed">{feature.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
