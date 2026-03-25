export const NODE_COLORS = {
    Customer:       '#10b981',
    SalesOrder:     '#3b82f6',
    SalesOrderItem: '#8b5cf6',
    Product:        '#f59e0b',
    Default:        '#94a3b8',
  };
  
  export function getNodeColor(label) {
    return NODE_COLORS[label] ?? NODE_COLORS.Default;
  }
  