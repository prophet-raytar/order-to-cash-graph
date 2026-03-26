import React, { useState, forwardRef } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { EntitySidebar } from './EntitySidebar';
import { usePaintNode } from './usePaintNode';

export const GraphPanel = forwardRef(({ graphData, highlightNodes, width, height, onExpandNode }, ref) => {
  const [hoverNode, setHoverNode] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  
  const paintNode = usePaintNode(highlightNodes, hoverNode);

  return (
    <div className="relative bg-slate-50 overflow-hidden" style={{ width, height }}>
      <ForceGraph2D
        ref={ref}
        width={width}
        height={height}
        graphData={graphData}
        nodeCanvasObject={paintNode}
        onNodeHover={setHoverNode}
        onNodeClick={setSelectedNode}
        onBackgroundClick={() => setSelectedNode(null)}
      />
      
      <EntitySidebar 
        node={selectedNode} 
        onClose={() => setSelectedNode(null)} 
        onExpand={onExpandNode}
      />
    </div>
  );
});