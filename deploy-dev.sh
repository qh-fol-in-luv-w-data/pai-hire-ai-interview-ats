#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .env.dev ]]; then
    echo "Thiếu .env.dev. Hãy copy .env.dev.example thành .env.dev và điền cấu hình."
    exit 1
fi

if [[ ! -f ats_phongvan_dev.db ]]; then
    touch ats_phongvan_dev.db
    echo "Đã tạo database dev: ats_phongvan_dev.db"
fi

mkdir -p outputs_dev/interviews outputs_dev/cv_applications outputs_dev/temp_pushbacks outputs_dev/question_audio

echo "Đang khởi động môi trường dev..."
sudo docker compose -p pai-hire-dev -f docker-compose.dev.yml up -d --build

echo "Dev đã khởi động: frontend http://localhost:8100, backend http://localhost:8101"
