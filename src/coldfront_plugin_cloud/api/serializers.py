from rest_framework import serializers

from coldfront.core.allocation.models import Allocation
from coldfront.core.allocation.models import Project

from coldfront_plugin_cloud import attributes


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = [
            'id',
            'title',
            'pi',
            'description',
            'field_of_science',
            'status'
        ]

    pi = serializers.SerializerMethodField()
    field_of_science = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    def get_pi(self, obj: Project) -> str:
        return obj.pi.username

    def get_field_of_science(self, obj: Project) -> str:
        return obj.field_of_science.description

    def get_status(self, obj: Project) -> str:
        return obj.status.name


class AllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Allocation
        fields = [
            'id',
            'project',
            'description',
            'resource',
            'status',
            'attributes'
        ]

    resource = serializers.SerializerMethodField()
    project = ProjectSerializer()
    attributes = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    def get_resource(self, obj: Allocation) -> dict:
        resource = obj.resources.first()
        return {
            'name': resource.name,
            'resource_type': resource.resource_type.name
        }

    def get_attributes(self, obj: Allocation):
        return {
            attr: obj.get_attribute(attr) for attr in attributes.ALLOCATION_ATTRIBUTES
        }

    def get_status(self, obj: Allocation) -> str:
        return obj.status.name
