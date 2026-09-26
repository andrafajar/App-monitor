set -euo pipefail
API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)
SEC=$(python3 -c "print([l.split('=',1)[1].strip().strip('\"').strip(\"'\") for l in open('/app/backend/.env') if l.startswith('WEBHOOK_CRON_SECRET')][0])")
TOKEN=$(curl -s -X POST "$API/api/auth/login" -H 'Content-Type: application/json' -d '{"email":"admin@netpulse.local","password":"Np-6oFKw7vnJ0Gr"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
auth() { curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$@"; }
DEV=mr-2be66e62

echo "== two scans to build rates + registry =="
auth -X POST "$API/api/devices/$DEV/snmp/scan" >/dev/null; sleep 6
auth -X POST "$API/api/devices/$DEV/snmp/scan" | python3 -c "import sys,json;d=json.load(sys.stdin);print('rates',[(i['name'],i['rx_mbps']) for i in d['snmp']['interfaces']])"
auth "$API/api/devices/$DEV/snmp" | python3 -c "import sys,json;d=json.load(sys.stdin);print('record config',d['config']['record_mode'],d['config']['recorded'])"

echo "== cron twice (writes interface history) =="
curl -s -X POST "$API/api/cron/monitor-scan" -H "Authorization: Bearer $SEC" -H "X-Webhook-Id: h1-$RANDOM" >/dev/null; sleep 20
curl -s -X POST "$API/api/cron/monitor-scan" -H "Authorization: Bearer $SEC" -H "X-Webhook-Id: h2-$RANDOM" >/dev/null; sleep 20
auth "$API/api/cron/runs" | python3 -c "import sys,json;r=json.load(sys.stdin)['items'][0];print('cron', r['job'], r.get('result'))"

echo "== interface history =="
auth "$API/api/devices/$DEV/interface-history?iface=eth0&hours=24" | python3 -c "import sys,json;d=json.load(sys.stdin);print('samples',d['samples'],'bucket',d['bucket_seconds'],'retention',d['retention_days']);print('traffic',d['traffic'][:3]);print('ping',d['ping'][:2]);print('avg',d['average'],'peak',d['peak'])"
auth "$API/api/devices/$DEV/interface-history?hours=999999&iface=eth0" | python3 -c "import sys,json;d=json.load(sys.stdin);print('clamped hours',d['hours'],'bucket',d['bucket_seconds'])"

echo "== manual selection validation =="
auth -o /dev/null -w "manual-empty:%{http_code}\n" -X PUT "$API/api/devices/$DEV/snmp/recorded" -d '{"mode":"manual","interfaces":[]}'
auth -o /dev/null -w "manual-unknown:%{http_code}\n" -X PUT "$API/api/devices/$DEV/snmp/recorded" -d '{"mode":"manual","interfaces":["nope0"]}'
auth -X PUT "$API/api/devices/$DEV/snmp/recorded" -d '{"mode":"manual","interfaces":["eth0","eth0","lo"]}' | python3 -c "import sys,json;print('dedup ->', json.load(sys.stdin)['config']['recorded'])"
auth -X PUT "$API/api/devices/$DEV/snmp/recorded" -d '{"mode":"auto","interfaces":["eth0"]}' | python3 -c "import sys,json;print('back to auto ->', json.load(sys.stdin)['config'])"
curl -s -X POST "$API/api/cron/monitor-scan" -H "Authorization: Bearer $SEC" -H "X-Webhook-Id: h3-$RANDOM" >/dev/null; sleep 12
auth "$API/api/devices/$DEV/snmp" | python3 -c "import sys,json;print('registry after auto scan ->', json.load(sys.stdin)['config']['recorded'])"

echo "== mikrotik device also records via snmp only when enabled =="
auth "$API/api/devices/mr-65920574/snmp" | python3 -c "import sys,json;d=json.load(sys.stdin);print('mikrotik snmp',d['config'],'ping',d['ping']['ms'])"

echo "== display carousel =="
auth -X PUT "$API/api/workspaces/ws-default/public-display" -d '{"enabled":true,"show_ips":false,"title":"NOC – Central Operations","rotate":false,"carousel":true,"carousel_seconds":8}' | python3 -c "import sys,json;print('display cfg', json.load(sys.stdin)['display'])"
TOK=$(auth "$API/api/workspaces/ws-default/public-display" | python3 -c "import sys,json;print(json.load(sys.stdin)['display']['token'])")
curl -s "$API/api/public/display/$TOK" | python3 -c "import sys,json;d=json.load(sys.stdin);print('public display',d['display'],'topology nodes',len(d['topology']['nodes']),'devices',len(d['devices']))"
echo "PUBLIC_PATH=/display/$TOK"
