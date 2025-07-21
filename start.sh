rm -rf ./torrents/*
alembic upgrade head
uvicorn main:app --reload --log-level info --host 0.0.0.0
