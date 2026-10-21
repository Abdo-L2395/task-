FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY nyc_taxi_cleaning.py .

CMD ["python", "nyc_taxi_cleaning.py", "--input", "/data/yellow_tripdata_2021-01.csv.gz"]
