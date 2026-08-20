"""WebSocket URL routing — phase 6.

Kept separate from ``config/urls.py`` because the two are consumed by different halves of
``config/asgi.py`` and a Channels route is not a Django view.
"""

from django.urls import path

from crm_app.consumers import RealtimeConsumer

websocket_urlpatterns = [
    # One endpoint. Upstream's socket.io namespace was the site name; there is one site
    # here, so the path carries no identifier.
    path("ws/realtime", RealtimeConsumer.as_asgi()),
]
