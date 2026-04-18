import os
import django
from django.core.management import call_command
from pathlib import Path


# def install_dependencies():
#     """安装依赖"""
#     pyproject_file = Path("pyproject.toml")

#     if pyproject_file.exists():
#         print("📦 安装依赖...")

#         # 首先尝试使用uv sync安装
#         try:
#             subprocess.run([
#                 "uv", "sync", "--no-cache"
#             ], check=True)
#             print("✓ 依赖安装完成")
#             return
#         except subprocess.CalledProcessError:
#             print("⚠️  uv sync失败，尝试使用pip install方式")

#         # 如果sync失败，尝试使用pip install方式
#         try:
#             subprocess.run([
#                 "pip", "install", "-e", ".", "--no-cache-dir"
#             ], check=True)
#             print("✓ 依赖安装完成")
#             return
#         except subprocess.CalledProcessError:
#             print("⚠️  无法安装依赖")


def create_superuser():
    from django.contrib.auth import get_user_model
    from django.conf import settings

    User = get_user_model()
    existing_user = User.objects.filter(
        username=settings.DEFAULT_SUPERUSER_USERNAME
    ).first()

    if existing_user is None:
        User.objects.create_superuser(
            settings.DEFAULT_SUPERUSER_USERNAME,
            settings.DEFAULT_SUPERUSER_EMAIL,
            settings.DEFAULT_SUPERUSER_PASSWORD,
        )
        print(
            "✅ Successfully created a new superuser: "
            f"{settings.DEFAULT_SUPERUSER_USERNAME}"
        )
    elif existing_user.is_superuser:
        print(
            "ℹ️ Superuser already exists, but you can change the password by running "
            f"'python manage.py changepassword {settings.DEFAULT_SUPERUSER_USERNAME}' command."
        )
    else:
        print(
            "ℹ️ A user with the default superuser username already exists, "
            "skipping automatic superuser creation."
        )


def init_server():
    """初始化服务器的主函数"""
    # 安装依赖
    # install_dependencies()
    # 设置Django环境
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    print("Starting server initialization...")

    try:
        if os.environ.get("RUN_COLLECTSTATIC_ON_START", "1") == "1":
            print("Collecting static files...")
            call_command("collectstatic", interactive=False, verbosity=1)

        if os.environ.get("RUN_MAKEMIGRATIONS_ON_START", "1") == "1":
            print("Creating migrations...")
            call_command("makemigrations", verbosity=1)

        if os.environ.get("RUN_MIGRATIONS_ON_START", "1") == "1":
            print("Running migrations...")
            call_command("migrate", verbosity=0, interactive=False)

        if os.environ.get("RUN_CREATE_SUPERUSER_ON_START", "1") == "1":
            print("Creating default superuser...")
            create_superuser()

        if os.environ.get("RUN_COMPILEMESSAGES_ON_START", "1") == "1":
            print("Compiling messages...")
            try:
                call_command("compilemessages", verbosity=0)
            except Exception as e:
                print(f"Warning: Failed to compile messages: {e}")

        print("Server initialization completed successfully!")

    except Exception as e:
        import traceback

        print(f"Error: {e}\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    init_server()
