"""ASGI entry point.

Phase 6 makes this the interesting one: WSGI cannot carry a WebSocket, so the deployed
process has to speak ASGI. HTTP still goes to the ordinary Django application — only the
``ws://`` half is new.

``ENABLE_REALTIME`` is the switch behind `PHASE_6_REALTIME.md` §4's last criterion:
*"Nothing in the app breaks when Channels is switched off."* With it off this file
returns the plain HTTP application and a WebSocket connect is refused by the server, not
by us — which is the honest failure and the one the client already handles as "no
realtime available".
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

# Must come before anything that imports models or the routing module.
django_asgi_app = get_asgi_application()


def _build_application():
    from django.conf import settings

    if not getattr(settings, "ENABLE_REALTIME", True):
        return django_asgi_app

    from channels.routing import ProtocolTypeRouter, URLRouter

    from config.routing import websocket_urlpatterns

    return ProtocolTypeRouter(
        {
            "http": django_asgi_app,
            # No `AuthMiddlewareStack`: there is no session cookie to read. The consumer
            # authenticates from the JWT itself (`PHASE_6_REALTIME.md` §3), so wrapping
            # it in cookie auth would only add a database hit per connect and imply an
            # authentication that is not happening.
            "websocket": URLRouter(websocket_urlpatterns),
        }
    )


application = _build_application()
