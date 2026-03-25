import React from 'react';
import { Sparkles } from 'lucide-react';
import { ChatMessage } from './ChatMessage';

export function MessageList({ messages, isLoading, chatEndRef }) {
  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.map((msg, idx) => (
        <ChatMessage key={idx} role={msg.role} content={msg.content} />
      ))}

      {isLoading && (
        <div className="flex justify-start animate-in fade-in slide-in-from-bottom-2 duration-300">
          <div className="bg-slate-100 border border-slate-200 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm flex items-center gap-3">
            {/* Glowing AI Icon */}
            <div className="relative flex items-center justify-center">
              <div className="absolute inset-0 bg-indigo-400 rounded-full blur animate-pulse opacity-50" />
              <Sparkles className="w-4 h-4 text-indigo-600 relative z-10 animate-pulse" />
            </div>
            
            {/* Bouncing Dots */}
            <div className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            
            <span className="text-sm font-medium text-slate-500 ml-1">
              Analyzing Graph...
            </span>
          </div>
        </div>
      )}

      {/* Invisible div to scroll to */}
      <div ref={chatEndRef} className="h-1" />
    </div>
  );
}