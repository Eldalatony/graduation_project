FROM python:3.11-slim

# Build tools needed for tenseal (Microsoft SEAL bindings) if no wheel is
# available for the target arch. They make the image larger but guarantee
# a successful build across platforms.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential cmake \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Unbuffered stdout so Docker logs show prints immediately.
CMD ["python", "-u", "app.py"]
