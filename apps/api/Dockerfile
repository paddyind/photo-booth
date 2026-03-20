FROM campus-circle-backend@sha256:c15109cd3fbf3910ca1313dfe25182b65ad53770fa601f90bf5ca00b98062469

WORKDIR /app

COPY apps/api /app/apps/api

CMD ["uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
