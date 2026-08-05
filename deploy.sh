#!/bin/bash

# Tạo file DB rỗng nếu chưa tồn tại để Docker không nhầm thành thư mục khi mount
if [ ! -f ats_phongvan.db ]; then
    touch ats_phongvan.db
    echo "Đã tạo file ats_phongvan.db rỗng."
fi

# Tạo thư mục outputs
mkdir -p outputs/interviews outputs/cv_applications outputs/temp_pushbacks outputs/question_audio

# Chạy docker-compose
echo "Đang khởi động Docker container..."
sudo docker compose up -d --build

echo "Deploy thành công! Frontend đang chạy tại port 8000, Backend API đang chạy tại port 8001."
