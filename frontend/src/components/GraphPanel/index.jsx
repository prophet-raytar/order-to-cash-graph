import React, { useState, forwardRef } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { NodeTooltip } from './NodeTooltip';
import { usePaintNode } from './usePaintNode';

export const GraphPanel = forwardRef(({ graphData, highlightNodes, width, height }, ref) => {
  const [hoverNode, setHoverNode] = useState(null);
  const paintNode = usePaintNode(highlightNodes, hoverNode);

  return (
    <div className="relative bg-slate-50" style={{ width, height }}>
      <ForceGraph2D
        ref={ref}
        width={width}
        height={height}
        graphData={graphData}
        nodeCanvasObject={paintNode}
        onNodeHover={setHoverNode}
      />
      <NodeTooltip node={hoverNode} />
    </div>
  );
});