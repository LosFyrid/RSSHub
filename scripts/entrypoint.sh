#!/bin/sh

# 将环境变量写入cron可以访问的文件
echo "Exporting environment variables for cron..."
printenv | grep -Ev 'BASHOPTS|BASH_VERSINFO|EUID|PPID|SHELLOPTS|UID' >> /etc/environment

wait_for_postgres() {
  max_attempts=20
  attempt=0

  until [ $attempt -ge $max_attempts ] || python - <<'PY' 2>/dev/null
import os
import psycopg

database_url = os.environ.get("DATABASE_URL")
if database_url:
    conn = psycopg.connect(database_url)
else:
    conn = psycopg.connect(
        dbname=os.environ.get("POSTGRES_DB", "rsshub"),
        user=os.environ.get("POSTGRES_USER", "rsshub"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        connect_timeout=int(os.environ.get("POSTGRES_CONNECT_TIMEOUT", "5")),
    )
conn.close()
PY
  do
    attempt=$((attempt+1))
    echo "Waiting for Postgres... (Attempt $attempt/$max_attempts)"
    sleep 2
  done

  if [ $attempt -lt $max_attempts ]; then
    echo "Postgres is available!"
  else
    echo "Failed to connect to Postgres after $max_attempts attempts."
  fi
}

if [ "${DATABASE_BACKEND:-sqlite}" = "postgres" ] && [ "${WAIT_FOR_DB_ON_START:-1}" = "1" ]; then
  wait_for_postgres
fi

if [ "${RUN_INIT_ON_START:-1}" = "1" ]; then
  echo "Running initialization script..."
  /opt/venv/bin/python $DockerHOME/scripts/init.py
fi

if [ "${ENABLE_CONTAINER_CRON:-0}" = "1" ]; then
  cron -n &
fi

if [ "${WAIT_FOR_REDIS_ON_START:-1}" = "1" ]; then
  # 等待Redis服务可用
  REDIS_URL=${REDIS_URL:-redis://rssbox_redis:6379/0}
  max_attempts=10
  attempt=0

  until [ $attempt -ge $max_attempts ] || python -c "import redis; r=redis.Redis.from_url('$REDIS_URL'); r.ping()" 2>/dev/null; do
    attempt=$((attempt+1))
    echo "Waiting for Redis at $REDIS_URL... (Attempt $attempt/$max_attempts)"
    sleep 2
  done

  if [ $attempt -lt $max_attempts ]; then
    echo "Redis is available!"
  else
    echo "Failed to connect to Redis after $max_attempts attempts."
  fi
fi

exec "$@"
