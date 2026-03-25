import React, { useRef } from 'react';

import { useWindowSize }   from './hooks/useWindowSize.js';
import { useResizable }    from './hooks/useResizable.js';
import { useGraphData }    from './hooks/useGraphData.js';
import { useChatMessages } from './hooks/useChatMessages.js';

import { GraphPanel } from './components/GraphPanel';
import { ChatPanel }  from './components/ChatPanel';
import { DragHandle } from './components/DragHandle';

export default function App() {
  const fgRef = useRef();

  // Layout
  const { width: windowWidth, height: windowHeight } = useWindowSize();
  const { width: sidebarWidth, startDrag }           = useResizable(400);
  const graphWidth                                   = windowWidth - sidebarWidth;

  // Data
  const { graphData }                                              = useGraphData();
  const { messages, isLoading, highlightNodes, chatEndRef, sendMessage } = useChatMessages();

  const handleSend = async (text) => {
    const nodeIds = await sendMessage(text);
    if (nodeIds?.length && fgRef.current) {
      fgRef.current.zoomToFit(
        400,
        50,
        (n) => nodeIds.includes(n.id) || nodeIds.includes(n.properties?.id),
      );
    }
  };

  return (
    <div className="flex h-screen w-full bg-slate-50 font-sans overflow-hidden">
      <GraphPanel
        ref={fgRef}
        graphData={graphData}
        highlightNodes={highlightNodes}
        width={graphWidth}
        height={windowHeight}
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