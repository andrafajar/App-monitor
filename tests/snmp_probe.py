import asyncio, sys
sys.path.insert(0, "/app/backend")


async def main():
    from monitor import ping_device, snmp_get, snmp_walk, SYS_OIDS
    print("ping 127.0.0.1 ->", await ping_device("127.0.0.1"))
    print("ping 8.8.8.8 ->", await ping_device("8.8.8.8"))
    print("ping 10.255.255.1 ->", await ping_device("10.255.255.1"))
    for host, community in (("103.102.13.4", "public"), ("127.0.0.1", "public")):
        try: print(host, "snmp sys ->", await snmp_get(host, 161, community, SYS_OIDS))
        except Exception as exc: print(host, "snmp failed ->", type(exc).__name__, str(exc)[:120])
    try: print("walk ifDescr ->", list((await snmp_walk("103.102.13.4", 161, "public", "1.3.6.1.2.1.2.2.1.2")).items())[:5])
    except Exception as exc: print("walk failed ->", type(exc).__name__, str(exc)[:120])


asyncio.run(main())
