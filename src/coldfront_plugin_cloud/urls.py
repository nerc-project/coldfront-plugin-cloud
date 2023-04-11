import os

from rest_framework import routers, viewsets
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAdminUser
from mozilla_django_oidc.contrib.drf import OIDCAuthentication

from coldfront.core.allocation.models import Allocation

from coldfront_plugin_cloud.api import serializers

if os.getenv('PLUGIN_OIDC') == 'True':
    AUTHENTICATION_CLASSES = [OIDCAuthentication]
else:
    AUTHENTICATION_CLASSES = [SessionAuthentication, BasicAuthentication]


class AllocationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Allocation.objects.filter(status__name='Active')
    serializer_class = serializers.AllocationSerializer
    authentication_classes = AUTHENTICATION_CLASSES
    permission_classes = [IsAdminUser]


router = routers.SimpleRouter()
router.register(r'allocations', AllocationViewSet)

urlpatterns = router.urls
