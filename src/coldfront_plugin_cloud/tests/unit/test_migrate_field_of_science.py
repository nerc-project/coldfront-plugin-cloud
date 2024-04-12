import uuid
import tempfile

from django.core.management import call_command
from coldfront.core.project.models import Project
from coldfront.core.field_of_science.models import FieldOfScience

from coldfront_plugin_cloud.tests import base


class TestFixAllocation(base.TestBase):
    def test_command_output(self):
        old_fos_1 = self.new_field_of_science()
        old_fos_2 = self.new_field_of_science()
        old_fos_3 = self.new_field_of_science()
        old_fos_4 = self.new_field_of_science()

        new_fos_1_des = uuid.uuid4().hex  # Migrate to new fos
        new_fos_2_des = old_fos_4.description  # Migrate to existing fos

        fake_project_1 = self.new_project()
        fake_project_2 = self.new_project()
        fake_project_3 = self.new_project()
        fake_project_1.field_of_science = old_fos_1
        fake_project_2.field_of_science = old_fos_2
        fake_project_3.field_of_science = old_fos_3
        fake_project_1.save()
        fake_project_2.save()
        fake_project_3.save()

        temp_csv = tempfile.NamedTemporaryFile(mode="w+")
        temp_csv.write(f"{old_fos_1.description}\t{new_fos_1_des}\n")
        temp_csv.write(f"{old_fos_2.description}\t{new_fos_2_des}\n")
        temp_csv.write(f"{old_fos_3.description}\t{new_fos_2_des}\n")
        temp_csv.seek(0)

        n_fos = FieldOfScience.objects.all().count()
        call_command("migrate_fields_of_science", "-m", temp_csv.name)

        self.assertEqual(n_fos - 2, FieldOfScience.objects.all().count())

        # Assert project fos name replaced
        fake_project_1 = Project.objects.get(pk=fake_project_1.pk)
        fake_project_2 = Project.objects.get(pk=fake_project_2.pk)
        fake_project_3 = Project.objects.get(pk=fake_project_3.pk)
        self.assertEqual(fake_project_1.field_of_science.description, new_fos_1_des)
        self.assertEqual(fake_project_2.field_of_science.description, new_fos_2_des)
        self.assertEqual(fake_project_3.field_of_science.description, new_fos_2_des)

        # Assert old fos no longer exists
        self.assertFalse(
            FieldOfScience.objects.filter(description=old_fos_1.description)
        )
        self.assertFalse(
            FieldOfScience.objects.filter(description=old_fos_2.description)
        )
        self.assertFalse(
            FieldOfScience.objects.filter(description=old_fos_3.description)
        )
