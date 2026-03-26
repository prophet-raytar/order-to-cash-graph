import React, { useRef } from 'react';

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

      // 2. Zoom to the highlighted nodes
      const nodeIds = responseData.highlight_nodes || [];
      if (nodeIds.length && fgRef.current) {
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
  const handleExpandNode = async (nodeId) => {
    console.log(`[Step 1] Expand button clicked for Node ID: ${nodeId}`);
    
    try {
      console.log(`[Step 2] Sending request to http://localhost:8000/api/expand/${nodeId}`);
      const response = await fetch(`http://localhost:8000/api/expand/${encodeURIComponent(nodeId)}`);
      
      if (!response.ok) {
        throw new Error(`Backend returned status ${response.status}`);
      }
      
      const newData = await response.json();
      console.log(`[Step 3] Backend replied with ${newData.nodes.length} nodes and ${newData.links.length} links.`);

      // --- THE FIX: Check for duplicates OUTSIDE the React state updater ---
      const currentNodes = graphData.nodes || [];
      const existingNodeIdsForCheck = new Set(currentNodes.map(n => n.id));
      const hasNewNodes = newData.nodes.some(n => !existingNodeIdsForCheck.has(n.id));

      if (!hasNewNodes) {
        alert("All connections for this node are already visible on the graph!");
        return; // Kills the function instantly so React doesn't double-render!
      }

      // 2. Surgically merge the new data
      setGraphData(prevData => {
        const existingNodeIds = new Set(prevData.nodes.map(n => n.id));
        const existingLinkIds = new Set(prevData.links.map(l => `${l.source.id || l.source}-${l.target.id || l.target}`));

        const newNodes = newData.nodes.filter(n => !existingNodeIds.has(n.id));
        const newLinks = newData.links.filter(l => !existingLinkIds.has(`${l.source}-${l.target}`));

        console.log(`[Step 4] After filtering duplicates, injecting ${newNodes.length} completely new nodes!`);

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
        ref={fgRef}
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