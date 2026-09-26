export const RESOURCE_COLUMNS = {
  Logs: ["time", "topics", "message"],
  Interfaces: ["name", "type", "mac-address", "running", "disabled", "comment"],
  Addresses: ["address", "network", "interface", "disabled", "comment"],
  ARP: ["address", "mac-address", "interface", "dynamic", "complete", "comment"],
  "DHCP Server": ["name", "interface", "address-pool", "lease-time", "disabled"],
  "DHCP Leases": ["address", "mac-address", "host-name", "server", "status", "expires-after", "comment"],
  Firewall: ["chain", "action", "src-address", "dst-address", "protocol", "dst-port", "disabled", "comment"],
  NAT: ["chain", "action", "src-address", "dst-address", "protocol", "dst-port", "to-addresses", "to-ports", "disabled", "comment"],
  Routes: ["dst-address", "gateway", "distance", "active", "static", "disabled", "comment"],
  "PPP Profiles": ["name", "local-address", "remote-address", "rate-limit", "dns-server"],
  "PPP Secrets": ["name", "service", "profile", "password", "remote-address", "disabled", "comment"],
  Queues: ["name", "target", "max-limit", "burst-limit", "disabled", "comment"],
  Wireless: ["interface", "mac-address", "signal-strength", "tx-rate", "rx-rate", "uptime"],
  "System Time": ["time", "date", "time-zone-name", "gmt-offset", "dst-active"],
  "System Resource": ["uptime", "version", "board-name", "cpu-load", "free-memory", "total-memory"],
  "System Identity": ["name"],
  "System Health": ["name", "value", "type"],
};

export const RESOURCE_KEY = {
  Logs: "logs", Interfaces: "interfaces", Addresses: "addresses", ARP: "arp",
  "DHCP Server": "dhcp-server", "DHCP Leases": "dhcp-leases", Firewall: "firewall", NAT: "nat", Routes: "routes",
  "PPP Profiles": "ppp-profiles", "PPP Secrets": "ppp-secrets", Queues: "queues", Wireless: "wireless-registration",
  "System Time": "system-clock", "System Resource": "system-resource", "System Identity": "system-identity", "System Health": "system-health",
};

// Editable properties per category (RouterOS property names). type: text | yesno | select
const YN = { type: "yesno" };
export const EDITABLE_FIELDS = {
  Interfaces: [{ key: "name" }, { key: "mtu" }, { key: "comment" }, { key: "disabled", ...YN }],
  Addresses: [{ key: "address", placeholder: "192.168.88.1/24", required: true }, { key: "interface", required: true }, { key: "comment" }, { key: "disabled", ...YN }],
  ARP: [{ key: "address", required: true }, { key: "mac-address", required: true }, { key: "interface", required: true }, { key: "comment" }],
  "DHCP Server": [{ key: "name", required: true }, { key: "interface", required: true }, { key: "address-pool" }, { key: "lease-time", placeholder: "10m" }, { key: "disabled", ...YN }],
  "DHCP Leases": [{ key: "address", required: true }, { key: "mac-address", required: true }, { key: "server" }, { key: "comment" }],
  Firewall: [{ key: "chain", type: "select", options: ["input", "forward", "output"], required: true }, { key: "action", type: "select", options: ["accept", "drop", "reject", "log", "jump", "fasttrack-connection", "passthrough", "return"], required: true }, { key: "src-address" }, { key: "dst-address" }, { key: "protocol" }, { key: "dst-port" }, { key: "in-interface" }, { key: "out-interface" }, { key: "comment" }, { key: "disabled", ...YN }],
  NAT: [{ key: "chain", type: "select", options: ["srcnat", "dstnat"], required: true }, { key: "action", type: "select", options: ["masquerade", "dst-nat", "src-nat", "accept", "redirect", "netmap", "passthrough", "return"], required: true }, { key: "src-address" }, { key: "dst-address" }, { key: "protocol" }, { key: "dst-port" }, { key: "to-addresses" }, { key: "to-ports" }, { key: "out-interface" }, { key: "in-interface" }, { key: "comment" }, { key: "disabled", ...YN }],
  Routes: [{ key: "dst-address", placeholder: "0.0.0.0/0", required: true }, { key: "gateway", required: true }, { key: "distance", placeholder: "1" }, { key: "comment" }, { key: "disabled", ...YN }],
  "PPP Profiles": [{ key: "name", required: true }, { key: "local-address" }, { key: "remote-address" }, { key: "rate-limit", placeholder: "10M/10M" }, { key: "dns-server" }],
  "PPP Secrets": [{ key: "name", required: true }, { key: "password", type: "password" }, { key: "service", type: "select", options: ["any", "pppoe", "pptp", "l2tp", "ovpn", "sstp"] }, { key: "profile" }, { key: "remote-address" }, { key: "comment" }, { key: "disabled", ...YN }],
  Queues: [{ key: "name", required: true }, { key: "target", placeholder: "192.168.88.10/32", required: true }, { key: "max-limit", placeholder: "5M/10M" }, { key: "burst-limit" }, { key: "comment" }, { key: "disabled", ...YN }],
  "System Time": [{ key: "time", placeholder: "13:45:00" }, { key: "date", placeholder: "jan/01/2026" }, { key: "time-zone-name", placeholder: "Asia/Jakarta" }],
  "System Identity": [{ key: "name", required: true }],
};

export const SINGLE_OBJECT = new Set(["System Time", "System Identity", "System Resource"]);

export const WINBOX_MENU = [
  { section: "Interfaces", items: ["Interfaces", "Wireless"] },
  { section: "IP", items: ["Addresses", "ARP", "DHCP Server", "DHCP Leases", "Firewall", "NAT", "Routes"] },
  { section: "PPP", items: ["PPP Profiles", "PPP Secrets"] },
  { section: "Queues", items: ["Queues"] },
  { section: "System", items: ["System Identity", "System Resource", "System Time", "System Health"] },
  { section: "Log", items: ["Logs"] },
  { section: "Files", items: ["Backups"] },
  { section: "Tools", items: ["Terminal"] },
];

export const MODULE_LABELS = {
  overview: "Overview dashboard", routers: "Routers (inventory & read)", groups: "Device groups", alarms: "Alarms",
  audit: "Audit log", notifications: "Telegram notifications", backups: "Backups", users: "Users", roles: "Roles",
  workspaces: "Workspaces", ros_config: "RouterOS config writes (add/edit/remove)",
};
