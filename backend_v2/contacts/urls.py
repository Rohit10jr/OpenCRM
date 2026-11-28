from contacts.views import (
    AddressViewSet,
    ContactViewSet,
    CRMIndustryViewSet,
    CRMOrganizationViewSet,
    CRMTerritoryViewSet,
    GenderViewSet,
    SalutationViewSet,
)
from core.routers import DocumentRouter

router = DocumentRouter()
router.register("contacts", ContactViewSet, basename="contact")
router.register("addresses", AddressViewSet, basename="address")
router.register("salutations", SalutationViewSet, basename="salutation")
router.register("genders", GenderViewSet, basename="gender")
router.register("industries", CRMIndustryViewSet, basename="industry")
router.register("territories", CRMTerritoryViewSet, basename="territory")
router.register("organizations", CRMOrganizationViewSet, basename="organization")
urlpatterns = router.urls
