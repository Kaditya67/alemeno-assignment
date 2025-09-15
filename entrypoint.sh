#!/bin/sh

echo "Waiting for db..."
sleep 5   # crude wait, later we’ll add a robust check

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
