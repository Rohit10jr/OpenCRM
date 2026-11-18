from core.routers import DocumentRouter, SingletonRouter
from tests_support.views import (
    AutoIncrementDocumentViewSet,
    ContactHolderViewSet,
    DynamicReferenceViewSet,
    FieldDocumentViewSet,
    PointingDocumentViewSet,
    PromptDocumentViewSet,
    SearchableDocumentViewSet,
    SecuredDocumentViewSet,
    SingletonDocumentViewSet,
    StrayContactViewSet,
    WidgetViewSet,
)


router = DocumentRouter()
router.register("test-widgets", WidgetViewSet, basename="test-widget")
router.register(
    "test-searchable-documents",
    SearchableDocumentViewSet,
    basename="test-searchable-document",
)
router.register("test-pointers", PointingDocumentViewSet, basename="test-pointer")
router.register("test-contact-holders", ContactHolderViewSet, basename="test-contact-holder")
router.register("test-stray-contacts", StrayContactViewSet, basename="test-stray-contact")
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
