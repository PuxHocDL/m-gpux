import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function Billing() {
  const data = [
    { name: 'Mon', spend: 4.2 },
    { name: 'Tue', spend: 8.5 },
    { name: 'Wed', spend: 6.1 },
    { name: 'Thu', spend: 12.4 },
    { name: 'Fri', spend: 9.8 },
    { name: 'Sat', spend: 2.1 },
    { name: 'Sun', spend: 1.5 },
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-2">Billing & Usage</h1>
        <p className="text-muted">Monitor your compute spend across all Modal profiles.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-surface border border-border rounded-xl p-6">
          <div className="text-muted text-sm font-medium mb-2">Total Spend (This Week)</div>
          <div className="text-3xl font-bold">$44.60</div>
        </div>
        <div className="bg-surface border border-border rounded-xl p-6">
          <div className="text-muted text-sm font-medium mb-2">Active Profile</div>
          <div className="text-xl font-bold text-primary">personal-dev</div>
        </div>
        <div className="bg-surface border border-border rounded-xl p-6">
          <div className="text-muted text-sm font-medium mb-2">Projected Monthly</div>
          <div className="text-xl font-bold">$180.00</div>
        </div>
      </div>

      <div className="bg-surface border border-border rounded-xl p-6 h-[400px]">
        <h3 className="font-bold mb-6">Daily Compute Spend</h3>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" vertical={false} />
            <XAxis dataKey="name" stroke="#a1a1aa" fontSize={12} tickLine={false} axisLine={false} />
            <YAxis stroke="#a1a1aa" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(val) => `$${val}`} />
            <Tooltip 
              cursor={{ fill: 'rgba(249, 115, 22, 0.1)' }}
              contentStyle={{ backgroundColor: '#111111', borderColor: '#2a2a2a', borderRadius: '8px' }}
            />
            <Bar dataKey="spend" fill="#f97316" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
