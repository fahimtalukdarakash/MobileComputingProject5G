FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask
COPY edge.py /app/edge.py
# ENV FLASK_RUN_HOST=0.0.0.0 FLASK_RUN_PORT=5000
# EXPOSE 5000
CMD ["python", "/app/app.py"]
