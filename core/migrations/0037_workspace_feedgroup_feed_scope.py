from django.db import migrations, models
import django.db.models.deletion


def ensure_default_workspace(apps, schema_editor):
    Workspace = apps.get_model("core", "Workspace")
    Feed = apps.get_model("core", "Feed")

    workspace, _ = Workspace.objects.get_or_create(
        slug="default-workspace",
        defaults={
            "name": "Default Workspace",
            "description": "Auto-created default workspace",
            "default_target_language": "Chinese Simplified",
            "is_default": True,
            "is_active": True,
        },
    )
    Feed.objects.filter(workspace__isnull=True).update(workspace=workspace)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0036_openaiagent_merge_system_prompt"),
    ]

    operations = [
        migrations.CreateModel(
            name="Workspace",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, unique=True, verbose_name="Name")),
                ("slug", models.SlugField(max_length=50, unique=True, verbose_name="URL Slug")),
                ("description", models.TextField(blank=True, default="", verbose_name="Description")),
                ("default_target_language", models.CharField(default="Chinese Simplified", max_length=50, verbose_name="Default Target Language")),
                ("is_default", models.BooleanField(default=False, verbose_name="Default Workspace")),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
            ],
            options={
                "verbose_name": "Workspace",
                "verbose_name_plural": "Workspaces",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="FeedGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Name")),
                ("slug", models.SlugField(max_length=50, verbose_name="URL Slug")),
                ("description", models.TextField(blank=True, default="", verbose_name="Description")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="groups", to="core.workspace", verbose_name="Workspace")),
            ],
            options={
                "verbose_name": "Feed Group",
                "verbose_name_plural": "Feed Groups",
                "ordering": ["workspace__name", "name"],
            },
        ),
        migrations.AddField(
            model_name="feed",
            name="workspace",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="feeds",
                to="core.workspace",
                verbose_name="Workspace",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="feed",
            name="source_kind",
            field=models.CharField(
                choices=[("standard", "Standard RSS/Atom"), ("builderpulse", "BuilderPulse")],
                default="standard",
                max_length=32,
                verbose_name="Source Kind",
            ),
        ),
        migrations.AddField(
            model_name="feed",
            name="source_ref",
            field=models.CharField(
                blank=True,
                help_text="Adapter-specific source reference, used by synthetic sources.",
                max_length=255,
                null=True,
                verbose_name="Source Reference",
            ),
        ),
        migrations.AddField(
            model_name="feed",
            name="groups",
            field=models.ManyToManyField(blank=True, related_name="feeds", to="core.feedgroup", verbose_name="Groups"),
        ),
        migrations.AlterField(
            model_name="feed",
            name="feed_url",
            field=models.URLField(blank=True, null=True, verbose_name="Feed URL"),
        ),
        migrations.RunPython(ensure_default_workspace, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="feed",
            name="unique_feed_lang",
        ),
        migrations.AddConstraint(
            model_name="feedgroup",
            constraint=models.UniqueConstraint(fields=("workspace", "name"), name="unique_workspace_group_name"),
        ),
        migrations.AddConstraint(
            model_name="feed",
            constraint=models.UniqueConstraint(
                condition=models.Q(("feed_url__isnull", False)),
                fields=("workspace", "feed_url", "target_language"),
                name="unique_workspace_feed_lang",
            ),
        ),
        migrations.AddConstraint(
            model_name="feed",
            constraint=models.UniqueConstraint(
                condition=models.Q(("source_ref__isnull", False)),
                fields=("workspace", "source_kind", "source_ref", "target_language"),
                name="unique_workspace_source_ref_lang",
            ),
        ),
    ]
