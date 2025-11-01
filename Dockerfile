# Dockerfile for deploying the Flask application
FROM python:3.13

WORKDIR /app

COPY requirements.txt .

RUN  pip install -r ./requirements.txt

COPY . /app

CMD ["python", "run_telegram.py"]
