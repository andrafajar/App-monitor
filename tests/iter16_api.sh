set -euo pipefail
API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)
SEC=$(python3 -c "print([l.split('=',1)[1].strip().strip('\"').strip(\"'\") for l in open('/app/backend/.env') if l.startswith('WEBHOOK_CRON_SECRET')][0])")
TOKEN=$(curl -s -X POST "$API/api/auth/login" -H 'Content-Type: application/json' -d '{"email":"admin@netpulse.local","password":"Np-6oFKw7vnJ0Gr"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
auth() { curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$@"; }
DEV=mr-2be66e62

echo "== alias in snmp scan =="
auth -X POST "$API/api/devices/$DEV/snmp/scan" | python3 -c "import sys,json;d=json.load(sys.stdin);print([(i['name'],i.get('alias'),i['status']) for i in d['snmp']['interfaces']])"
auth "$API/api/topology/interfaces" | python3 -c "import sys,json;print([(i['name'],[(x['name'],x.get('alias')) for x in i['interfaces']]) for i in json.load(sys.stdin)['items']])"

echo "== thresholds =="
auth -o /dev/null -w "enable-without-limit:%{http_code}\n" -X PUT "$API/api/devices/$DEV/snmp/thresholds" -d '{"enabled":true,"rx_mbps":0,"tx_mbps":0,"loss_pct":0}'
auth -X PUT "$API/api/devices/$DEV/snmp/thresholds" -d '{"enabled":true,"rx_mbps":0.001,"tx_mbps":0,"loss_pct":0}' | python3 -c "import sys,json;print('armed ->', json.load(sys.stdin)['config']['thresholds'])"
curl -s -X POST "$API/api/cron/monitor-scan" -H "Authorization: Bearer $SEC" -H "X-Webhook-Id: thr-$RANDOM" >/dev/null; sleep 18
auth "$API/api/cron/runs" | python3 -c "import sys,json;r=json.load(sys.stdin)['items'][0];print('cron alarms ->', r.get('result',{}).get('alarms'))"
auth "$API/api/alarms" | python3 -c "
import sys,json;d=json.load(sys.stdin)
rows=[a for a in d.get('items',[]) if a.get('kind')=='threshold'][:2]
print('threshold alarms ->', [(a['router_name'], a['detail'][:80]) for a in rows] or 'none yet')"
auth -X PUT "$API/api/devices/$DEV/snmp/thresholds" -d '{"enabled":false,"rx_mbps":0,"tx_mbps":0,"loss_pct":0}' | python3 -c "import sys,json;print('disarmed ->', json.load(sys.stdin)['config']['thresholds'])"

echo "== topology link edit =="
LINK=$(auth -X POST "$API/api/topology/links" -d "{\"a_device\":\"$DEV\",\"a_iface\":\"eth0\",\"b_device\":\"$DEV\",\"b_iface\":\"lo\",\"label\":\"before\"}")
LID=$(echo "$LINK" | python3 -c "import sys,json;print(json.load(sys.stdin)['link']['id'])")
auth -X PUT "$API/api/topology/links/$LID" -d "{\"a_device\":\"$DEV\",\"a_iface\":\"lo\",\"b_device\":\"$DEV\",\"b_iface\":\"eth0\",\"label\":\"after edit\"}" | python3 -c "import sys,json;print('edited ->', json.load(sys.stdin)['link'])"
auth -o /dev/null -w "edit-unknown-iface:%{http_code}\n" -X PUT "$API/api/topology/links/$LID" -d "{\"a_device\":\"$DEV\",\"a_iface\":\"zzz9\",\"b_device\":\"$DEV\",\"b_iface\":\"eth0\",\"label\":\"x\"}"
auth -o /dev/null -w "edit-missing-link:%{http_code}\n" -X PUT "$API/api/topology/links/lnk-nope" -d "{\"a_device\":\"$DEV\",\"a_iface\":\"lo\",\"b_device\":\"$DEV\",\"b_iface\":\"eth0\",\"label\":\"x\"}"
auth "$API/api/topology" | python3 -c "import sys,json;print('links ->', [(l['id'],l['a_iface'],l['b_iface'],l['label'],l['status']) for l in json.load(sys.stdin)['links']])"
auth -o /dev/null -w "delete-link:%{http_code}\n" -X DELETE "$API/api/topology/links/$LID"
