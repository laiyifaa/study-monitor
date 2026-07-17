FROM python:3.11-slim

WORKDIR /app

# 安装 tesseract-ocr 系统包（用于图片方向检测，可选依赖）
RUN apt-get update && \
    apt-get install -y --no-install-recommends tesseract-ocr && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# 使用清华镜像源加速 pip 安装，增加超时时间防止国内网络下载中断
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 120 -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
