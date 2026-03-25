import { useState, useEffect } from 'react';

const MIN_WIDTH = 300;
const MAX_WIDTH = 800;
const DEFAULT_WIDTH = 400;

export function useResizable(initialWidth = DEFAULT_WIDTH) {
  const [width, setWidth]         = useState(initialWidth);
  const [isDragging, setDragging] = useState(false);

  const startDrag = () => setDragging(true);

  useEffect(() => {
    if (!isDragging) return;

    const onMove = (e) => {
      const next = window.innerWidth - e.clientX;
      if (next > MIN_WIDTH && next < MAX_WIDTH) setWidth(next);
    };
    const onUp = () => setDragging(false);

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',   onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup',   onUp);
    };
  }, [isDragging]);

  return { width, isDragging, startDrag };
}
