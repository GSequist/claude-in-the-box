from auth import get_auth_headers
from config import INSTANCE_DOMAINS
import httpx


async def fire_host_cleanup():
    """
    calls HOST /maintenance only if HOST is alive
    """
    for host_domain in INSTANCE_DOMAINS.values():
        print(f"[LAMBDA] Checking if HOST {host_domain} is alive...")

        # Check if host is up first
        try:
            async with httpx.AsyncClient() as client:
                health_check = await client.get(
                    f"https://{host_domain}/health",
                    timeout=2.0,
                )

                if health_check.status_code != 200:
                    print(f"⏭️ Host {host_domain} is down, skipping HOST maintenance")
                    return

        except Exception as e:
            print(
                f"⏭️ Host {host_domain} is unreachable, skipping HOST maintenance: {e}"
            )
            return

        # Host is up, run maintenance
        print(f"[LAMBDA] Host is alive, triggering HOST maintenance...")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://{host_domain}/maintenance",
                    headers=get_auth_headers(),
                    timeout=5.0,
                )

                if response.status_code == 200:
                    print(f"✅ HOST maintenance triggered")
                else:
                    print(f"⚠️ Host returned {response.status_code}")

        except Exception as e:
            print(f"❌ [LAMBDA] Error calling HOST maintenance: {e}")
            import traceback

            traceback.print_exc()
