import React, { useState, useEffect, useRef, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { Send, Loader2, Database, MessageSquare, GripVertical } from 'lucide-react';

export default function App() {
  // --- Data & Chat State ---
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Hi! I am your Order-to-Cash AI. Ask me to trace an order, find a product, or analyze the flow.' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  // --- Graph Interaction State ---
  const [highlightNodes, setHighlightNodes] = useState(new Set());
  const [hoverNode, setHoverNode] = useState(null);
  const fgRef = useRef();
  const chatEndRef = useRef(null);

  // --- Layout & Resizing State ---
  const [sidebarWidth, setSidebarWidth] = useState(400);
  const [isDragging, setIsDragging] = useState(false);
  const [windowSize, setWindowSize] = useState({ width: window.innerWidth, height: window.innerHeight });

  // 1. Initial Data Load
  useEffect(() => {
    fetch('http://127.0.0.1:8000/api/graph')
      .then(res => res.json())
      .then(data => setGraphData(data))
      .catch(err => console.error("Failed to load graph:", err));
  }, []);

  // 2. Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 3. Keep track of window size so the Canvas never overflows
  useEffect(() => {
    const handleResize = () => setWindowSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // 4. Drag to Resize Logic
  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isDragging) return;
      const newWidth = window.innerWidth - e.clientX;
      if (newWidth > 300 && newWidth < 800) {
        setSidebarWidth(newWidth);
      }
    };
    const handleMouseUp = () => setIsDragging(false);

    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    }
  }, [isDragging]);

  // --- Chat Handler ---
  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setIsLoading(true);
    setHighlightNodes(new Set());

    try {
      const response = await fetch('http://127.0.0.1:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMsg, history: messages })
      });
      
      const data = await response.json();
      setMessages(prev => [...prev, { role: 'assistant', content: data.answer }]);
      
      if (data.highlight_nodes && data.highlight_nodes.length > 0) {
        setHighlightNodes(new Set(data.highlight_nodes));
        if (fgRef.current) {
          // Tell the camera to look at BOTH the Neo4j ID and the Business ID
          fgRef.current.zoomToFit(400, 50, n => 
            data.highlight_nodes.includes(n.id) || 
            data.highlight_nodes.includes(n.properties?.id)
          );
        }
      }
    } catch (error) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Network error communicating with the database.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  // --- High-Performance Canvas Rendering ---
  const paintNode = useCallback((node, ctx, globalScale) => {
    // Check if the highlighted list contains the Neo4j ID OR the Business ID
    const isMatch = highlightNodes.has(node.id) || highlightNodes.has(node.properties?.id);
    const isHighlighted = highlightNodes.size === 0 || isMatch;
    const isHovered = hoverNode === node;

    const colors = {
      Customer: '#10b981',
      SalesOrder: '#3b82f6',
      SalesOrderItem: '#8b5cf6',
      Product: '#f59e0b',
      Default: '#94a3b8'
    };
    
    ctx.beginPath();
    ctx.arc(node.x, node.y, 5, 0, 2 * Math.PI, false);
    ctx.fillStyle = isHighlighted ? (colors[node.label] || colors.Default) : '#e2e8f0';
    ctx.fill();

    if (isHovered || (highlightNodes.has(node.id) && highlightNodes.size > 0)) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, 8, 0, 2 * Math.PI, false);
      ctx.strokeStyle = colors[node.label] || colors.Default;
      ctx.lineWidth = 1.5 / globalScale;
      ctx.stroke();
    }
    
    if (globalScale > 2 && isHighlighted) {
      const label = node.properties?.id || node.id;
      const fontSize = 12 / globalScale;
      ctx.font = `${fontSize}px Sans-Serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#1e293b';
      ctx.fillText(label, node.x, node.y + 8);
    }
  }, [highlightNodes, hoverNode]);

  const graphWidth = windowSize.width - sidebarWidth;

  return (
    <div className="flex h-screen w-full bg-slate-50 font-sans overflow-hidden">
      
      {/* LEFT PANEL: The Graph */}
      <div className="relative h-full bg-white" style={{ width: graphWidth }}>
        <div className="absolute top-0 left-0 w-full p-4 bg-gradient-to-b from-white to-transparent z-10 pointer-events-none flex items-center gap-2">
          <Database className="w-5 h-5 text-indigo-600" />
          <h1 className="text-xl font-semibold text-slate-800 tracking-tight">Mapping / <span className="text-slate-500 font-normal">Order to Cash</span></h1>
        </div>

        <ForceGraph2D
          ref={fgRef}
          width={graphWidth}
          height={windowSize.height}
          graphData={graphData}
          nodeCanvasObject={paintNode}
          linkColor={() => '#cbd5e1'}
          linkOpacity={0.4}
          linkWidth={1}
          onNodeHover={setHoverNode}
          warmupTicks={100}
          cooldownTicks={0}
        />

        {/* Hover Tooltip */}
        {hoverNode && (
          <div className="absolute top-16 left-6 bg-white p-4 rounded-xl shadow-xl border border-slate-100 min-w-[250px] pointer-events-none z-20">
            <h3 className="font-bold text-slate-800 mb-2 border-b pb-2 flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full bg-indigo-500`} />
              {hoverNode.label}
            </h3>
            <div className="space-y-1 text-sm">
              {Object.entries(hoverNode.properties || {}).map(([key, val]) => (
                <div key={key} className="flex justify-between gap-4">
                  <span className="text-slate-500 font-medium">{key}:</span>
                  <span className="text-slate-900 truncate max-w-[150px]" title={val}>{String(val)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* DRAG HANDLE */}
      <div 
        className="w-1.5 h-full bg-slate-200 hover:bg-indigo-400 cursor-col-resize z-30 transition-colors flex items-center justify-center group"
        onMouseDown={() => setIsDragging(true)}
      >
        <div className="h-8 w-4 bg-white border border-slate-300 rounded flex items-center justify-center shadow-sm opacity-0 group-hover:opacity-100 transition-opacity absolute">
           <GripVertical className="w-3 h-3 text-slate-400" />
        </div>
      </div>

      {/* RIGHT PANEL: Chat Interface */}
      <div 
        className="h-full bg-white flex flex-col shadow-[-10px_0_15px_-3px_rgba(0,0,0,0.05)] z-20"
        style={{ width: sidebarWidth }}
      >
        <div className="p-4 border-b border-slate-100 flex items-center gap-3 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white">
            <MessageSquare className="w-4 h-4" />
          </div>
          <div>
            <h2 className="font-semibold text-slate-800">Chat with Graph</h2>
            <p className="text-xs text-slate-500">Order to Cash Assistant</p>
          </div>
        </div>

        {/* Message History */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg, idx) => (
            <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              
              {/* --- FDE FIX: ADDED whitespace-pre-wrap RIGHT HERE --- */}
              <div className={`max-w-[85%] rounded-2xl p-3 text-sm leading-relaxed whitespace-pre-wrap ${
                msg.role === 'user' 
                  ? 'bg-indigo-600 text-white rounded-br-none shadow-sm' 
                  : 'bg-slate-100 text-slate-800 rounded-bl-none'
              }`}>
                {msg.content}
              </div>
              
            </div>
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-slate-100 rounded-2xl rounded-bl-none p-3 text-slate-500 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-sm">Querying database...</span>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Input Area */}
        <div className="p-4 bg-white border-t border-slate-100 shrink-0">
          <form onSubmit={handleSendMessage} className="relative flex items-center">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about orders, products, flow..."
              className="w-full bg-slate-50 border border-slate-200 rounded-xl py-3 pl-4 pr-12 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="absolute right-2 p-2 text-white bg-slate-800 rounded-lg hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
          <div className="mt-3 text-center flex items-center justify-center gap-1.5 text-xs text-slate-400">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            AI is connected and awaiting instructions
          </div>
        </div>
      </div>
      
    </div>
  );
}