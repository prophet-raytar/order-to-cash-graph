import { useState, useEffect, useRef } from 'react';
import { sendChatMessage } from '../api/client';

const INITIAL_MESSAGES = [
  {
    role: 'assistant',
    content:
      'Hi! I am your Order-to-Cash AI. Ask me to trace an order, find a product, or analyze the flow.',
  },
];

export function useChatMessages() {
  const [messages,       setMessages]       = useState(INITIAL_MESSAGES);
  const [isLoading,      setIsLoading]      = useState(false);
  const [highlightNodes, setHighlightNodes] = useState(new Set());
  const chatEndRef = useRef(null);

  // Auto-scroll to bottom whenever messages change
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async (userText) => {
    if (!userText.trim()) return null;

    setMessages((prev) => [...prev, { role: 'user', content: userText }]);
    setIsLoading(true);
    setHighlightNodes(new Set());

    try {
      const data = await sendChatMessage(userText, messages);
      setMessages((prev) => [...prev, { role: 'assistant', content: data.answer }]);

      if (data.highlight_nodes?.length) {
        setHighlightNodes(new Set(data.highlight_nodes));
        return data.highlight_nodes; // caller uses this to zoom the graph
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Network error communicating with the database.' },
      ]);
    } finally {
      setIsLoading(false);
    }

    return null;
  };

  return { messages, isLoading, highlightNodes, chatEndRef, sendMessage };
}
