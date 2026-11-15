from core.routers import DocumentRouter, SingletonRouter
from tests_support.views import (
    AutoIncrementDocumentViewSet,
    DynamicReferenceViewSet,
    FieldDocumentViewSet,
    PointingDocumentViewSet,
    PromptDocumentViewSet,
    SecuredDocumentViewSet,
    SingletonDocumentViewSet,
    WidgetViewSet,
)


router = DocumentRouter()
router.register("test-widgets", WidgetViewSet, basename="test-widget")
router.register("test-pointers", PointingDocumentViewSet, basename="test-pointer")
router.register(
    "test-dynamic-references",
    DynamicReferenceViewSet,
    basename="test-dynamic-reference",
)
router.register("test-fields", FieldDocumentViewSet, basename="test-field")
router.register("test-secured", SecuredDocumentViewSet, basename="test-secured")
router.register("test-prompts", PromptDocumentViewSet, basename="test-prompt")
router.register(
    "test-auto-increments",
    AutoIncrementDocumentViewSet,
    basename="test-auto-increment",
)

urlpatterns = router.urls

singleton_router = SingletonRouter()
singleton_router.register(
    "test-singleton", SingletonDocumentViewSet, basename="test-singleton"
)
urlpatterns += singleton_router.urls
