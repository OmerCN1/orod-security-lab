FROM python:3.12-slim

RUN pip install --no-cache-dir bandit==1.9.4 ruff==0.16.4 pytest==9.1.1
COPY entrypoint.py /opt/orod/entrypoint.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 HOME=/tmp
USER 65532:65532
WORKDIR /workspace
ENTRYPOINT ["python", "-I", "/opt/orod/entrypoint.py"]
