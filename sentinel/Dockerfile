FROM python:3.9-slim

WORKDIR /app

# 安装依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝代码
COPY sentinel.py .

# 启动命令
CMD ["python", "sentinel.py"]
