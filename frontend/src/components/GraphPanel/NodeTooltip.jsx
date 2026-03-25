import React from 'react';
import { Hash, Calendar, Box, User, Tag, Info } from 'lucide-react';

// Utility to make raw database keys readable (e.g., 'customer_id' -> 'Customer Id')
const formatKey = (key) => {
  return key
    .replace(/_/g, ' ')
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, (str) => str.toUpperCase())
    .trim();
};

// Smart icon selector based on property names
const getIcon = (key) => {
  const k = key.toLowerCase();
  if (k.includes('id')) return <Hash className="w-3.5 h-3.5 text-slate-400" />;
  if (k.includes('date') || k.includes('time')) return <Calendar className="w-3.5 h-3.5 text-slate-400" />;
  if (k.includes('name') || k.includes('customer')) return <User className="w-3.5 h-3.5 text-slate-400" />;
  if (k.includes('product') || k.includes('item')) return <Box className="w-3.5 h-3.5 text-slate-400" />;
  return <Tag className="w-3.5 h-3.5 text-slate-400" />;
};

export function NodeTooltip({ node }) {
  if (!node) return null;

  return (
    <div className="absolute top-6 left-6 bg-white/95 backdrop-blur-md p-5 rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.12)] border border-slate-200/60 min-w-[320px] max-w-[400px] pointer-events-none z-20 transition-all duration-200 ease-in-out">
      
      {/* Header Section */}
      <div className="flex items-start gap-3 mb-4 pb-4 border-b border-slate-100">
        <div className="mt-1 w-3 h-3 rounded-full bg-indigo-500 shadow-sm shrink-0" />
        <div>
          <h3 className="font-bold text-slate-900 text-base leading-tight">{node.label}</h3>
          <p className="text-xs text-slate-500 font-medium font-mono mt-1 break-all">
            {node.id}
          </p>
        </div>
      </div>

      {/* Properties Grid */}
      <div className="space-y-3">
        {Object.entries(node.properties ?? {}).map(([key, val]) => (
          <div key={key} className="flex items-start justify-between gap-6 group">
            <div className="flex items-center gap-2 text-slate-500 shrink-0">
              {getIcon(key)}
              <span className="text-sm font-medium">{formatKey(key)}</span>
            </div>
            <span 
              className="text-sm text-slate-900 font-medium text-right break-words max-w-[180px]" 
              title={String(val)}
            >
              {String(val)}
            </span>
          </div>
        ))}
        
        {/* Empty State Fallback */}
        {Object.keys(node.properties ?? {}).length === 0 && (
          <div className="flex items-center gap-2 text-slate-400 text-sm italic">
            <Info className="w-4 h-4" />
            No additional properties found
          </div>
        )}
      </div>
    </div>
  );
}