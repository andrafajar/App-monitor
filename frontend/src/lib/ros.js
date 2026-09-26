export const RESOURCE_COLUMNS = {
  Logs: ["time", "topics", "message"],
  Interfaces: ["name", "type", "mac-address", "running", "disabled", "comment"],
  Bridge: ["name", "protocol-mode", "vlan-filtering", "priority", "running", "disabled", "comment"],
  "Bridge Ports": ["interface", "bridge", "pvid", "horizon", "learn", "disabled", "comment"],
  VLAN: ["name", "vlan-id", "interface", "mtu", "running", "disabled", "comment"],
  Wireless: ["name", "mode", "ssid", "band", "frequency", "security-profile", "running", "disabled"],
  "Wireless Security": ["name", "mode", "authentication-types", "unicast-ciphers", "group-ciphers"],
  Registration: ["interface", "mac-address", "signal-strength", "tx-rate", "rx-rate", "uptime"],
  Addresses: ["address", "network", "interface", "disabled", "comment"],
  ARP: ["address", "mac-address", "interface", "dynamic", "complete", "comment"],
  "IP Pools": ["name", "ranges", "next-pool", "comment"],
  "DHCP Server": ["name", "interface", "address-pool", "lease-time", "disabled"],
  "DHCP Leases": ["address", "mac-address", "host-name", "server", "status", "expires-after", "comment"],
  Firewall: ["chain", "action", "src-address", "dst-address", "protocol", "dst-port", "disabled", "comment"],
  NAT: ["chain", "action", "src-address", "dst-address", "protocol", "dst-port", "to-addresses", "to-ports", "disabled", "comment"],
  Routes: ["dst-address", "gateway", "distance", "active", "static", "disabled", "comment"],
  "PPP Profiles": ["name", "local-address", "remote-address", "rate-limit", "dns-server"],
  "PPP Secrets": ["name", "service", "profile", "password", "remote-address", "disabled", "comment"],
  "Hotspot Servers": ["name", "interface", "address-pool", "profile", "addresses-per-mac", "disabled"],
  "Hotspot Profiles": ["name", "hotspot-address", "dns-name", "html-directory", "login-by"],
  "Hotspot Users": ["name", "password", "profile", "server", "limit-uptime", "bytes-in", "bytes-out", "disabled", "comment"],
  "Hotspot User Profiles": ["name", "rate-limit", "shared-users", "session-timeout", "idle-timeout"],
  "Hotspot Active": ["user", "address", "mac-address", "uptime", "session-time-left", "bytes-in", "bytes-out"],
  Queues: ["name", "target", "max-limit", "burst-limit", "disabled", "comment"],
  "System Time": ["time", "date", "time-zone-name", "gmt-offset", "dst-active"],
  "System Resource": ["uptime", "version", "board-name", "cpu-load", "free-memory", "total-memory"],
  "System Identity": ["name"],
  "System Health": ["name", "value", "type"],
};

export const RESOURCE_KEY = {
  Logs: "logs", Interfaces: "interfaces", Bridge: "bridge", "Bridge Ports": "bridge-ports", VLAN: "vlan",
  Wireless: "wireless", "Wireless Security": "wireless-security", Registration: "wireless-registration",
  Addresses: "addresses", ARP: "arp", "IP Pools": "ip-pools", "DHCP Server": "dhcp-server", "DHCP Leases": "dhcp-leases",
  Firewall: "firewall", NAT: "nat", Routes: "routes",
  "PPP Profiles": "ppp-profiles", "PPP Secrets": "ppp-secrets",
  "Hotspot Servers": "hotspot-servers", "Hotspot Profiles": "hotspot-profiles", "Hotspot Users": "hotspot-users",
  "Hotspot User Profiles": "hotspot-user-profiles", "Hotspot Active": "hotspot-active",
  Queues: "queues",
  "System Time": "system-clock", "System Resource": "system-resource", "System Identity": "system-identity", "System Health": "system-health",
};

// Categories whose rows contain secrets — password columns stay redacted until the user reveals them.
export const SENSITIVE_TABS = new Set(["PPP Secrets", "Hotspot Users"]);

// Live pick-lists read from the router itself, so reference fields are dropdowns instead of free typing.
export const REFERENCE_SOURCES = {
  interfaces: { resource: "interfaces", label: "name" },
  bridges: { resource: "bridge", label: "name" },
  pools: { resource: "ip-pools", label: "name" },
  "dhcp-servers": { resource: "dhcp-server", label: "name" },
  "ppp-profiles": { resource: "ppp-profiles", label: "name" },
  "wireless-security": { resource: "wireless-security", label: "name" },
  "hotspot-servers": { resource: "hotspot-servers", label: "name" },
  "hotspot-profiles": { resource: "hotspot-profiles", label: "name" },
  "hotspot-user-profiles": { resource: "hotspot-user-profiles", label: "name" },
};

// Editable properties per category (RouterOS property names). type: text | yesno | select | password; source: pick-list from the router
const YN = { type: "yesno" };
export const EDITABLE_FIELDS = {
  Interfaces: [{ key: "name" }, { key: "mtu" }, { key: "comment" }, { key: "disabled", ...YN }],
  Bridge: [{ key: "name", required: true }, { key: "protocol-mode", type: "select", options: ["none", "rstp", "stp", "mstp"] }, { key: "vlan-filtering", ...YN }, { key: "priority", placeholder: "0x8000" }, { key: "comment" }, { key: "disabled", ...YN }],
  "Bridge Ports": [{ key: "interface", source: "interfaces", required: true }, { key: "bridge", source: "bridges", required: true }, { key: "pvid", placeholder: "1" }, { key: "horizon" }, { key: "learn", type: "select", options: ["auto", "yes", "no"] }, { key: "comment" }, { key: "disabled", ...YN }],
  VLAN: [{ key: "name", required: true, placeholder: "vlan10" }, { key: "vlan-id", required: true, placeholder: "10" }, { key: "interface", source: "interfaces", required: true }, { key: "mtu" }, { key: "comment" }, { key: "disabled", ...YN }],
  Wireless: [{ key: "ssid" }, { key: "mode", type: "select", options: ["ap-bridge", "bridge", "station", "station-bridge", "station-pseudobridge"] }, { key: "band", type: "select", options: ["2ghz-b/g/n", "2ghz-g/n", "5ghz-a/n/ac", "5ghz-n/ac", "5ghz-a/n"] }, { key: "frequency", placeholder: "auto" }, { key: "channel-width" }, { key: "security-profile", source: "wireless-security" }, { key: "comment" }, { key: "disabled", ...YN }],
  "Wireless Security": [{ key: "name", required: true }, { key: "mode", type: "select", options: ["none", "dynamic-keys", "static-keys-optional", "static-keys-required"] }, { key: "authentication-types", placeholder: "wpa2-psk" }, { key: "wpa2-pre-shared-key", type: "password" }, { key: "wpa-pre-shared-key", type: "password" }],
  Addresses: [{ key: "address", placeholder: "192.168.88.1/24", required: true }, { key: "interface", source: "interfaces", required: true }, { key: "comment" }, { key: "disabled", ...YN }],
  ARP: [{ key: "address", required: true }, { key: "mac-address", required: true }, { key: "interface", source: "interfaces", required: true }, { key: "comment" }],
  "IP Pools": [{ key: "name", required: true }, { key: "ranges", required: true, placeholder: "192.168.88.10-192.168.88.254" }, { key: "next-pool" }, { key: "comment" }],
  "DHCP Server": [{ key: "name", required: true }, { key: "interface", source: "interfaces", required: true }, { key: "address-pool", source: "pools" }, { key: "lease-time", placeholder: "10m" }, { key: "disabled", ...YN }],
  "DHCP Leases": [{ key: "address", required: true }, { key: "mac-address", required: true }, { key: "server", source: "dhcp-servers" }, { key: "comment" }],
  Firewall: [{ key: "chain", type: "select", options: ["input", "forward", "output"], required: true }, { key: "action", type: "select", options: ["accept", "drop", "reject", "log", "jump", "fasttrack-connection", "passthrough", "return"], required: true }, { key: "src-address" }, { key: "dst-address" }, { key: "protocol" }, { key: "dst-port" }, { key: "in-interface", source: "interfaces" }, { key: "out-interface", source: "interfaces" }, { key: "comment" }, { key: "disabled", ...YN }],
  NAT: [{ key: "chain", type: "select", options: ["srcnat", "dstnat"], required: true }, { key: "action", type: "select", options: ["masquerade", "dst-nat", "src-nat", "accept", "redirect", "netmap", "passthrough", "return"], required: true }, { key: "src-address" }, { key: "dst-address" }, { key: "protocol" }, { key: "dst-port" }, { key: "to-addresses" }, { key: "to-ports" }, { key: "out-interface", source: "interfaces" }, { key: "in-interface", source: "interfaces" }, { key: "comment" }, { key: "disabled", ...YN }],
  Routes: [{ key: "dst-address", placeholder: "0.0.0.0/0", required: true }, { key: "gateway", required: true }, { key: "distance", placeholder: "1" }, { key: "comment" }, { key: "disabled", ...YN }],
  "PPP Profiles": [{ key: "name", required: true }, { key: "local-address" }, { key: "remote-address" }, { key: "rate-limit", placeholder: "10M/10M" }, { key: "dns-server" }],
  "PPP Secrets": [{ key: "name", required: true }, { key: "password", type: "password" }, { key: "service", type: "select", options: ["any", "pppoe", "pptp", "l2tp", "ovpn", "sstp"] }, { key: "profile", source: "ppp-profiles" }, { key: "remote-address" }, { key: "comment" }, { key: "disabled", ...YN }],
  "Hotspot Servers": [{ key: "name", required: true }, { key: "interface", source: "interfaces", required: true }, { key: "address-pool", source: "pools" }, { key: "profile", source: "hotspot-profiles" }, { key: "addresses-per-mac" }, { key: "disabled", ...YN }],
  "Hotspot Profiles": [{ key: "name", required: true }, { key: "hotspot-address" }, { key: "dns-name" }, { key: "html-directory", placeholder: "hotspot" }, { key: "login-by", placeholder: "http-chap" }],
  "Hotspot Users": [{ key: "name", required: true }, { key: "password", type: "password" }, { key: "profile", source: "hotspot-user-profiles" }, { key: "server", source: "hotspot-servers" }, { key: "limit-uptime", placeholder: "1h" }, { key: "comment" }, { key: "disabled", ...YN }],
  "Hotspot User Profiles": [{ key: "name", required: true }, { key: "rate-limit", placeholder: "2M/2M" }, { key: "shared-users", placeholder: "1" }, { key: "session-timeout" }, { key: "idle-timeout" }],
  Queues: [{ key: "name", required: true }, { key: "target", placeholder: "192.168.88.10/32", required: true }, { key: "max-limit", placeholder: "5M/10M" }, { key: "burst-limit" }, { key: "comment" }, { key: "disabled", ...YN }],
  "System Time": [{ key: "time", placeholder: "13:45:00" }, { key: "date", placeholder: "jan/01/2026" }, { key: "time-zone-name", placeholder: "Asia/Jakarta" }],
  "System Identity": [{ key: "name", required: true }],
};

export const SINGLE_OBJECT = new Set(["System Time", "System Identity", "System Resource"]);

export const WINBOX_MENU = [
  { section: "Interfaces", items: ["Interfaces", "Traffic", "Bridge", "Bridge Ports", "VLAN"] },
  { section: "Wireless", items: ["Wireless", "Wireless Security", "Registration"] },
  { section: "IP", items: ["Addresses", "ARP", "IP Pools", "DHCP Server", "DHCP Leases", "Firewall", "NAT", "Routes"] },
  { section: "Hotspot", items: ["Hotspot Servers", "Hotspot Profiles", "Hotspot Users", "Hotspot User Profiles", "Hotspot Active"] },
  { section: "PPP", items: ["PPP Profiles", "PPP Secrets"] },
  { section: "Queues", items: ["Queues"] },
  { section: "System", items: ["System Identity", "System Resource", "System Time", "System Health"] },
  { section: "Log", items: ["Logs"] },
  { section: "Files", items: ["Backups"] },
  { section: "Tools", items: ["Terminal (SSH)", "Terminal (API)"] },
];

export const PANEL_TABS = ["Backups", "Terminal (SSH)", "Terminal (API)", "Traffic"];

export const MODULE_LABELS = {
  overview: "Overview dashboard", routers: "Routers (inventory & read)", groups: "Device groups", alarms: "Alarms",
  audit: "Audit log", notifications: "Telegram notifications", backups: "Backups", users: "Users", roles: "Roles",
  workspaces: "Workspaces", ros_config: "RouterOS config writes (add/edit/remove)",
};
