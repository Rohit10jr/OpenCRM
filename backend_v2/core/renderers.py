"""Success envelopes; error bodies remain at the top level."""

from rest_framework.renderers import JSONRenderer

_ERROR_KEYS = {"exc_type", "_server_messages"}


class Envelope:
    __slots__ = ("extra", "key", "payload")

    def __init__(self, payload, key: str = "data", extra: dict | None = None):
        self.payload = payload
        self.key = key
        self.extra = extra or {}


class WithResponseKeys:
    __slots__ = ("keys", "message")

    def __init__(self, message=None, **keys):
        self.message = message
        self.keys = keys


class FrappeEnvelopeRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, Envelope):
            data = {data.key: data.payload, **data.extra}
        elif isinstance(data, dict) and _ERROR_KEYS & set(data):
            pass
        return super().render(data, accepted_media_type, renderer_context)
