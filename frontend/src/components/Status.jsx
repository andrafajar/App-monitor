export function Status({ value }) {
  const map = { online: ["Online", "status-online"], warning: ["Warning", "status-warning"], offline: ["Offline", "status-offline"], pending: ["Pending", "status-pending"], managed: ["Pending", "status-pending"] };
  const [label, cls] = map[value] || map.offline;
  return <span data-testid={`router-status-${value}`} className={`status ${cls}`}><i />{label}</span>;
}
