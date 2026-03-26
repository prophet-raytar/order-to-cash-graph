import React, { useState, useEffect } from 'react';
import { X, Hash, Calendar, Box, User, Tag, Info, Code, LayoutList, Network } from 'lucide-react';

const formatKey = (key) => {
  return key
    .replace(/_/g, ' ')
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, (str) => str.toUpperCase())
    .trim();
};

const getIcon = (key) => {
  const k = key.toLowerCase();
  if (k.includes('id')) return <Hash className="w-4 h-4 text-indigo-400" />;
  if (k.includes('date') || k.includes('time')) return <Calendar className="w-4 h-4 text-emerald-500" />;
  if (k.includes('name') || k.includes('customer')) return <User className="w-4 h-4 text-blue-500" />;
  if (k.includes('product') || k.includes('item')) return <Box className="w-4 h-4 text-amber-500" />;
  return <Tag className="w-4 h-4 text-slate-400" />;
};

// Notice we explicitly accept onExpand here!
export function EntitySidebar({ node, onClose, onExpand }) {
  const isOpen = !!node;
  const [showJson, setShowJson] = useState(false);

  useEffect(() => {
    setShowJson(false);
  }, [node]);

  return (
    <div 
      className={`absolute top-0 right-0 h-full w-80 bg-white/95 backdrop-blur-xl shadow-[-10px_0_30px_rgba(0,0,0,0.1)] border-l border-slate-200/60 z-50 transform transition-transform duration-300 ease-in-out flex flex-col ${
        isOpen ? 'translate-x-0' : 'translate-x-full'
      }`}
    >
      {node && (
        <>
          <div className="p-5 border-b border-slate-100 flex items-start justify-between shrink-0 bg-white">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <div className="w-2.5 h-2.5 rounded-full bg-indigo-500 shadow-sm" />
                <h2 className="font-bold text-slate-900 text-lg leading-tight">{node.label}</h2>
              </div>
              <p className="text-xs text-slate-500 font-mono break-all pr-4">{node.id}</p>
            </div>
            <button 
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-5 space-y-3">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
              {showJson ? 'Raw Payload Properties' : 'Entity Properties'}
            </h3>
            
            {showJson ? (
              <div className="bg-slate-900 rounded-xl p-4 overflow-x-auto shadow-inner">
                {/* We strictly stringify node.properties to avoid physics engine crashes */}
                <pre className="text-xs text-emerald-400 font-mono leading-relaxed">
                  {JSON.stringify(node.properties || {}, null, 2)}
                </pre>
              </div>
            ) : (
              <>
                {Object.entries(node.properties ?? {}).map(([key, val]) => (
                  <div key={key} className="bg-slate-50 rounded-xl p-3 border border-slate-100 hover:border-indigo-100 transition-colors">
                    <div className="flex items-center gap-2 mb-1.5">
                      {getIcon(key)}
                      <span className="text-xs font-medium text-slate-500">{formatKey(key)}</span>
                    </div>
                    <div className="text-sm font-semibold text-slate-800 break-words">
                      {String(val)}
                    </div>
                  </div>
                ))}

                {Object.keys(node.properties ?? {}).length === 0 && (
                  <div className="flex flex-col items-center justify-center py-10 text-slate-400 text-sm text-center">
                    <Info className="w-8 h-8 mb-2 opacity-40" />
                    No additional properties found
                  </div>
                )}
              </>
            )}
          </div>
          
          <div className="p-4 border-t border-slate-100 bg-slate-50 shrink-0 flex gap-2">
            <button 
              className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg shadow-sm hover:bg-indigo-700 transition-colors"
              onClick={() => onExpand(node.id)}
            >
              <Network className="w-4 h-4" />
              Expand Node
            </button>
            
            <button 
              className="w-10 flex items-center justify-center py-2.5 bg-white border border-slate-200 text-slate-700 rounded-lg shadow-sm hover:bg-slate-100 transition-colors"
              onClick={() => setShowJson(!showJson)}
              title="Toggle JSON View"
            >
              {showJson ? <LayoutList className="w-4 h-4" /> : <Code className="w-4 h-4" />}
            </button>
          </div>
        </>
      )}
    </div>
  );
}