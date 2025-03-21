# Build stage
FROM python:3.10-slim as builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libusb-1.0-0-dev \
    libudev-dev \
    qt6-base-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Runtime stage
FROM python:3.10-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libusb-1.0-0 \
    libudev1 \
    qt6-base \
    && rm -rf /var/lib/apt/lists/*

# Copy from builder
COPY --from=builder /app /app
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV QT_QPA_PLATFORM=minimal

# Run as non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Command to run the application
CMD ["python", "usb_gui.py"]

