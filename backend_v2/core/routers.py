"""Routers for document resources whose names may contain slashes."""

from rest_framework.routers import Route, SimpleRouter


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


class SingletonRouter(SimpleRouter):
    """Route one settings document at the collection root, without a name."""

    routes = (
        Route(
            url=r"^{prefix}{trailing_slash}$",
            mapping={"get": "retrieve", "patch": "partial_update"},
            name="{basename}-detail",
            detail=False,
            initkwargs={"suffix": "Instance"},
        ),
        SimpleRouter.routes[1],  # collection actions such as ``value``
    )

    def __init__(self):
        super().__init__(trailing_slash=True)
        self.trailing_slash = "/?"
