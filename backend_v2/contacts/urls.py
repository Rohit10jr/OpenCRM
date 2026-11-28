from contacts.views import CRMIndustryViewSet, GenderViewSet, SalutationViewSet
from core.routers import DocumentRouter

router = DocumentRouter()
router.register("salutations", SalutationViewSet, basename="salutation")
router.register("genders", GenderViewSet, basename="gender")
router.register("industries", CRMIndustryViewSet, basename="industry")
urlpatterns = router.urls
