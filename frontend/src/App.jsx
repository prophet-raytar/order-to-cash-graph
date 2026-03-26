import React, { useRef } from 'react';

// Notice we only import this once now!
import { useWindowSize }   from './hooks/useWindowSize.js';
import { useResizable }    from './hooks/useResizable.js';
import { useGraphData }    from './hooks/useGraphData.js';
import { useChatMessages } from './hooks/useChatMessages.js';

import { GraphPanel } from './components/GraphPanel';
import { ChatPanel }  from './components/ChatPanel';
import { DragHandle } from './components/DragHandle';

export default function App() {
  const dimensions = useWindowSize();
  const { width: sidebarWidth, startDrag } = useResizable(400);
  
  // FIX 1: Create the reference for the graph camera
  const fgRef = useRef(); 
  
  // FIX 2: Destructure setGraphData so we can inject new nodes
  const { graphData, setGraphData } = useGraphData();
  const { messages, isLoading, highlightNodes, chatEndRef, sendMessage } = useChatMessages();

  const handleSend = async (text) => {
    const responseData = await sendMessage(text);
    
    if (responseData) {
      // 1. Auto-Inject new nodes from the chat!
      if (responseData.new_nodes?.length > 0) {
        setGraphData(prevData => {
          const existingNodeIds = new Set(prevData.nodes.map(n => n.id));
          const existingLinkIds = new Set(prevData.links.map(l => `${l.source.id || l.source}-${l.target.id || l.target}`));

          const newNodes = responseData.new_nodes.filter(n => !existingNodeIds.has(n.id));
          const newLinks = responseData.new_links.filter(l => !existingLinkIds.has(`${l.source}-${l.target}`));

          return {
            nodes: [...prevData.nodes, ...newNodes],
            links: [...prevData.links, ...newLinks]
          };
        });
      }

      // 2. Zoom to the highlighted nodes (with a Senior Engineer trick)
      const nodeIds = responseData.highlight_nodes || [];
      if (nodeIds.length && fgRef.current) {
        // We add a tiny delay. Because setGraphData is asynchronous, 
        // we must give React 100ms to draw the new nodes before we zoom to them!
        setTimeout(() => {
          fgRef.current.zoomToFit(
            400,
            50,
            (n) => nodeIds.includes(n.id) || nodeIds.includes(n.properties?.id)
          );
        }, 100);
      }
    }
  };

  // --- ENTERPRISE FIX: Lazy Loading Graph Expansion ---
  // --- ENTERPRISE FIX: Lazy Loading Graph Expansion (With Diagnostics) ---
  const handleExpandNode = async (nodeId) => {
    console.log(`[Step 1] Expand button clicked for Node ID: ${nodeId}`);
    
    try {
      // 1. Fetch the neighbors from our new backend endpoint
      console.log(`[Step 2] Sending request to http://localhost:8000/api/expand/${nodeId}`);
      const response = await fetch(`http://localhost:8000/api/expand/${encodeURIComponent(nodeId)}`);
      
      if (!response.ok) {
        throw new Error(`Backend returned status ${response.status}`);
      }
      
      const newData = await response.json();
      console.log(`[Step 3] Backend replied with ${newData.nodes.length} nodes and ${newData.links.length} links.`);

      // 2. Surgically merge the new data to avoid physics engine crashes
      setGraphData(prevData => {
        const existingNodeIds = new Set(prevData.nodes.map(n => n.id));
        const existingLinkIds = new Set(prevData.links.map(l => `${l.source.id || l.source}-${l.target.id || l.target}`));

        const newNodes = newData.nodes.filter(n => !existingNodeIds.has(n.id));
        const newLinks = newData.links.filter(l => !existingLinkIds.has(`${l.source}-${l.target}`));

        console.log(`[Step 4] After filtering duplicates, injecting ${newNodes.length} completely new nodes!`);

        // Give the user visual feedback if everything is already visible
        if (newNodes.length === 0) {
          alert("All connections for this node are already visible on the graph!");
          return prevData;
        }

        return {
          nodes: [...prevData.nodes, ...newNodes],
          links: [...prevData.links, ...newLinks]
        };
      });
      
    } catch (error) {
      console.error("[!] Expansion error:", error);
      alert(`Expansion Failed: Look at the Developer Console (F12) for details.\nError: ${error.message}`);
    }
  };
  return (
    <div className="flex h-screen w-full bg-slate-50 font-sans overflow-hidden">
      <GraphPanel
        ref={fgRef} // FIX 3: Attach the camera reference here
        graphData={graphData} 
        highlightNodes={highlightNodes}
        width={dimensions.width}
        height={dimensions.height}
        onExpandNode={handleExpandNode}
      />

      <DragHandle onMouseDown={startDrag} />

      <ChatPanel
        width={sidebarWidth}
        messages={messages}
        isLoading={isLoading}
        chatEndRef={chatEndRef}
        onSend={handleSend}
      />
    </div>
  );
}