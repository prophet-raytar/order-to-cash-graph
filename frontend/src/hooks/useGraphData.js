import { useState, useEffect } from 'react';
import { fetchGraph } from '../api/client';

export function useGraphData() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [error,     setError]     = useState(null);

  useEffect(() => {
    fetchGraph()
      .then(setGraphData)
      .catch((err) => {
        console.error('Failed to load graph:', err);
        setError(err.message);
      });
  }, []);

  return { graphData, error };
}
