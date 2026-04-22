FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Expose port 5000
EXPOSE 5000

# Set default data directory (can be overridden by environment variable)
ENV DATA_DIR=/data

CMD ["python", "app.py"]
