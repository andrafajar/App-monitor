set -euo pipefail
API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)
TOKEN=$(curl -s -X POST "$API/api/auth/login" -H 'Content-Type: application/json' -d '{"email":"admin@netpulse.local","password":"Np-6oFKw7vnJ0Gr"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
H="-H Authorization:Bearer_$TOKEN"
auth() { curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$@"; }
GROUP=$(auth "$API/api/groups" | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")

echo "== create huawei device (snmp against local agent) =="
CREATE=$(auth -X POST "$API/api/routers" -d "{\"name\":\"QA Huawei SNMP\",\"host\":\"127.0.0.1\",\"device_type\":\"huawei\",\"snmp_enabled\":true,\"snmp_community\":\"netpulse\",\"snmp_port\":1161,\"ssh_port\":2222,\"telnet_port\":2323,\"group_id\":\"$GROUP\",\"description\":\"qa\"}")
echo "$CREATE" | python3 -c "import sys,json;d=json.load(sys.stdin);r=d['router'];print('created', r['id'], r['device_type'], r['status'], 'snmp', r.get('snmp_enabled'), 'probe', d['probe'])"
DEV=$(echo "$CREATE" | python3 -c "import sys,json;print(json.load(sys.stdin)['router']['id'])")

echo "== reject mikrotik without credentials =="
auth -o /dev/null -w "mikrotik-no-creds:%{http_code}\n" -X POST "$API/api/routers" -d "{\"name\":\"Bad ROS\",\"host\":\"10.0.0.9\",\"device_type\":\"mikrotik\",\"group_id\":\"$GROUP\"}"
echo "== reject snmp without community =="
auth -o /dev/null -w "snmp-no-community:%{http_code}\n" -X POST "$API/api/routers" -d "{\"name\":\"Bad SNMP\",\"host\":\"10.0.0.8\",\"device_type\":\"cisco\",\"snmp_enabled\":true,\"group_id\":\"$GROUP\"}"

echo "== snmp config + scan =="
auth "$API/api/devices/$DEV/snmp" | python3 -c "import sys,json;d=json.load(sys.stdin);print('config',d['config'],'ifaces',len(d['snmp'].get('interfaces') or []))"
auth -X POST "$API/api/devices/$DEV/snmp/scan" | python3 -c "import sys,json;d=json.load(sys.stdin);print('scan ok',d['ok'],'ping',d['ping'],'ifaces',[(i['name'],i['status']) for i in d['snmp'].get('interfaces',[])])"
auth -X PUT "$API/api/devices/$DEV/snmp" -d '{"enabled":true,"port":1161}' | python3 -c "import sys,json;print('put snmp', json.load(sys.stdin))"

echo "== routeros menus blocked for non-mikrotik =="
auth -o /dev/null -w "resource-on-huawei:%{http_code}\n" "$API/api/routers/$DEV/resources/interfaces"

echo "== metrics + monitor status =="
auth -X POST "$API/api/cron/monitor-scan" -H "Authorization: Bearer $(grep WEBHOOK_CRON_SECRET /app/backend/.env | cut -d= -f2)" -o /dev/null -w "cron-wrong-token:%{http_code}\n" || true
curl -s -X POST "$API/api/cron/monitor-scan" -H "Authorization: Bearer $(grep WEBHOOK_CRON_SECRET /app/backend/.env | cut -d= -f2)" -H "X-Webhook-Id: qa-$RANDOM" | head -c 200; echo
sleep 9
auth "$API/api/devices/$DEV/metrics" | python3 -c "import sys,json;d=json.load(sys.stdin);print('metrics',len(d['items']),'retention',d['retention_days'],'last',d['items'][-1] if d['items'] else None)"
auth "$API/api/monitor/status" | python3 -c "import sys,json;d=json.load(sys.stdin);print('status rows',[(i['name'],i['device_type'],i['status'],i['snmp_enabled'],i['snmp_interfaces']) for i in d['items']])"

echo "== topology =="
auth "$API/api/topology/interfaces" | python3 -c "import sys,json;d=json.load(sys.stdin);print([(i['name'],len(i['interfaces']),i.get('error')) for i in d['items']])"
LINK=$(auth -X POST "$API/api/topology/links" -d "{\"a_device\":\"$DEV\",\"a_iface\":\"eth0\",\"b_device\":\"$DEV\",\"b_iface\":\"lo\",\"label\":\"QA link\"}")
echo "$LINK" | python3 -c "import sys,json;print('link', json.load(sys.stdin))"
LID=$(echo "$LINK" | python3 -c "import sys,json;print(json.load(sys.stdin)['link']['id'])")
auth -o /dev/null -w "duplicate-link:%{http_code}\n" -X POST "$API/api/topology/links" -d "{\"a_device\":\"$DEV\",\"a_iface\":\"eth0\",\"b_device\":\"$DEV\",\"b_iface\":\"lo\"}"
auth -X PUT "$API/api/topology/nodes/$DEV" -d '{"x":420,"y":260}' | python3 -c "import sys,json;print('node moved', json.load(sys.stdin))"
auth "$API/api/topology" | python3 -c "import sys,json;d=json.load(sys.stdin);print('nodes',[(n['name'],n['x'],n['y'],n['status']) for n in d['nodes']]);print('links',[(l['a_iface'],l['b_iface'],l['status'],l['rx_mbps']) for l in d['links']])"
auth -o /dev/null -w "delete-link:%{http_code}\n" -X DELETE "$API/api/topology/links/$LID"

echo "== cleanup =="
auth -o /dev/null -w "delete-device:%{http_code}\n" -X DELETE "$API/api/routers/$DEV"
