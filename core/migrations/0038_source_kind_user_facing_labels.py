from django.db import migrations


def rewrite_source_kinds_forward(apps, schema_editor):
    Feed = apps.get_model("core", "Feed")
    Feed.objects.filter(source_kind="standard").update(source_kind="translate")
    Feed.objects.filter(source_kind="builderpulse").update(source_kind="github_md")


def rewrite_source_kinds_backward(apps, schema_editor):
    Feed = apps.get_model("core", "Feed")
    Feed.objects.filter(source_kind="translate").update(source_kind="standard")
    Feed.objects.filter(source_kind="github_md").update(source_kind="builderpulse")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0037_workspace_feedgroup_feed_scope"),
    ]

    operations = [
        migrations.RunPython(
            rewrite_source_kinds_forward,
            rewrite_source_kinds_backward,
        ),
    ]
