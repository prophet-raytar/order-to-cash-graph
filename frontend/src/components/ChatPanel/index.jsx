import React from 'react';
import { MessageSquare } from 'lucide-react';
import { MessageList } from './MessageList';
import { ChatInput }   from './ChatInput';

export function ChatPanel({ width, messages, isLoading, chatEndRef, onSend }) {
  return (
    <div
      className="h-full bg-white flex flex-col shadow-[-10px_0_15px_-3px_rgba(0,0,0,0.05)] z-20"
      style={{ width }}
    >
      {/* Header */}
      <div className="p-4 border-b border-slate-100 flex items-center gap-3 shrink-0">
        <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white">
          <MessageSquare className="w-4 h-4" />
        </div>
        <div>
          <h2 className="font-semibold text-slate-800">Chat with Graph</h2>
          <p className="text-xs text-slate-500">Order to Cash Assistant</p>
        </div>
      </div>

      <MessageList messages={messages} isLoading={isLoading} chatEndRef={chatEndRef} />
      <ChatInput onSend={onSend} disabled={isLoading} />
    </div>
  );
}