from rest_framework import routers, viewsets

from coldfront.core.allocation.models import Allocation

from coldfront_plugin_cloud.api import serializers


class AllocationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Allocation.objects.filter(status__name='Active')
    serializer_class = serializers.AllocationSerializer


router = routers.SimpleRouter()
router.register(r'allocations', AllocationViewSet)

urlpatterns = router.urls
