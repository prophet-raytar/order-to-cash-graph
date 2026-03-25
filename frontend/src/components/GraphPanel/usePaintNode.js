import { useCallback } from 'react';
import { getNodeColor } from '../../utils/nodeColors';

/**
 * Returns a stable `paintNode` callback suitable for ForceGraph2D's
 * `nodeCanvasObject` prop.  Re-creates only when highlight or hover changes.
 */
export function usePaintNode(highlightNodes, hoverNode) {
  return useCallback(
    (node, ctx, globalScale) => {
      const isMatch       = highlightNodes.has(node.id) || highlightNodes.has(node.properties?.id);
      const isHighlighted = highlightNodes.size === 0 || isMatch;
      const isHovered     = hoverNode === node;
      const color         = getNodeColor(node.label);

      // Base circle
      ctx.beginPath();
      ctx.arc(node.x, node.y, 5, 0, 2 * Math.PI, false);
      ctx.fillStyle = isHighlighted ? color : '#e2e8f0';
      ctx.fill();

      // Ring on hover or explicit highlight
      if (isHovered || (isMatch && highlightNodes.size > 0)) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, 8, 0, 2 * Math.PI, false);
        ctx.strokeStyle   = color;
        ctx.lineWidth     = 1.5 / globalScale;
        ctx.stroke();
      }

      // Label at high zoom
      if (globalScale > 2 && isHighlighted) {
        const label    = node.properties?.id ?? node.id;
        const fontSize = 12 / globalScale;
        ctx.font          = `${fontSize}px Sans-Serif`;
        ctx.textAlign     = 'center';
        ctx.textBaseline  = 'middle';
        ctx.fillStyle     = '#1e293b';
        ctx.fillText(label, node.x, node.y + 8);
      }
    },
    [highlightNodes, hoverNode],
  );
}
