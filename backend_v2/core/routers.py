"""Routers for document resources whose names may contain slashes."""

from rest_framework.routers import SimpleRouter


class DocumentRouter(SimpleRouter):
    """Put actions before the catch-all document route and accept either slash form."""

    routes = (
        SimpleRouter.routes[0],  # collection
        SimpleRouter.routes[1],  # collection actions
        SimpleRouter.routes[3],  # document actions
        SimpleRouter.routes[2],  # document, including names containing slashes
    )

    def __init__(self):
        super().__init__(trailing_slash=True)
        self.trailing_slash = "/?"
