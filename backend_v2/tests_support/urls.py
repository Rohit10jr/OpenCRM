from core.routers import DocumentRouter
from tests_support.views import (
    AutoIncrementDocumentViewSet,
    FieldDocumentViewSet,
    PromptDocumentViewSet,
    SecuredDocumentViewSet,
    WidgetViewSet,
)


router = DocumentRouter()
router.register("test-widgets", WidgetViewSet, basename="test-widget")
router.register("test-fields", FieldDocumentViewSet, basename="test-field")
router.register("test-secured", SecuredDocumentViewSet, basename="test-secured")
router.register("test-prompts", PromptDocumentViewSet, basename="test-prompt")
router.register("test-auto-increments", AutoIncrementDocumentViewSet, basename="test-auto-increment")

urlpatterns = router.urls
