import React from 'react';
import { GripVertical } from 'lucide-react';

export function DragHandle({ onMouseDown }) {
  return (
    <div
      className="w-1.5 h-full bg-slate-200 hover:bg-indigo-400 cursor-col-resize z-30 transition-colors flex items-center justify-center group"
      onMouseDown={onMouseDown}
    >
      <div className="h-8 w-4 bg-white border border-slate-300 rounded flex items-center justify-center shadow-sm opacity-0 group-hover:opacity-100 transition-opacity absolute">
        <GripVertical className="w-3 h-3 text-slate-400" />
      </div>
    </div>
  );
}
