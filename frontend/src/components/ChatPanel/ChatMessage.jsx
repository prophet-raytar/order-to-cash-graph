import React from 'react';

export function ChatMessage({ role, content }) {
  const isUser = role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl p-3 text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? 'bg-indigo-600 text-white rounded-br-none shadow-sm'
            : 'bg-slate-100 text-slate-800 rounded-bl-none'
        }`}
      >
        {content}
      </div>
    </div>
  );
}