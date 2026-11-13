"""WebSocket routes present before NOTIFICATIONS supplies the real consumer."""

from channels.generic.websocket import AsyncWebsocketConsumer
from django.urls import path


class RejectRealtimeConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.close(code=4001)


websocket_urlpatterns = [
    path("ws/realtime", RejectRealtimeConsumer.as_asgi()),
]
