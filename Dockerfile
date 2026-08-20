FROM node:20-alpine AS frontend_builder

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend .
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (ffmpeg is required for audio processing)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-dejavu-core \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Cho phép backend phục vụ cùng bản React build khi truy cập trực tiếp cổng API.
COPY --from=frontend_builder /frontend/dist /app/frontend/dist
COPY frontend/code.html frontend/report_print.html /app/frontend/dist/

# Expose port
EXPOSE 8001

# Command to run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
