FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
COPY airport_investment_agent ./airport_investment_agent
RUN pip install --no-cache-dir .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "airport_investment_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
