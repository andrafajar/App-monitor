import asyncio, sys
sys.path.insert(0, "/app/backend")


async def main():
    from core import db, credential_box
    from monitor import ping_device, poll_snmp, monitor_device, purge_history
    device = {"id": "test-snmp-1", "name": "Local SNMP agent", "host": "127.0.0.1", "workspace_id": "ws-default", "group_id": "none",
              "device_type": "other", "snmp_enabled": True, "snmp_port": 1161,
              "snmp_community_enc": credential_box().encrypt(b"netpulse").decode()}
    print("ping ->", await ping_device("127.0.0.1"))
    first = await poll_snmp(device)
    print("poll1 error:", first.get("error"), "cpu:", first.get("cpu"), "sysname:", first.get("sysname")[:30], "ifaces:", len(first.get("interfaces") or []))
    print("sample:", [(i["name"], i["status"], i["rx_mbps"]) for i in (first.get("interfaces") or [])[:3]])
    await asyncio.sleep(4)
    second = await poll_snmp(device)
    print("poll2 rates:", [(i["name"], i["rx_mbps"], i["tx_mbps"]) for i in (second.get("interfaces") or [])[:3]])
    fired = await monitor_device(device, {"enabled": True, "notify_unreachable": True, "notify_interface": True, "throttle_minutes": 60})
    print("monitor fired:", fired)
    print("metrics stored:", await db.device_metrics.count_documents({"device_id": "test-snmp-1"}))
    print("retention run:", await purge_history())
    await db.device_metrics.delete_many({"device_id": "test-snmp-1"})
    await db.snmp_state.delete_many({"device_id": "test-snmp-1"})
    await db.interface_state.delete_many({"router_id": "test-snmp-1"})


asyncio.run(main())
