# NYC Taxi Data 

This repository contains the Python code for INF4058 Lab 3. The pipeline profiles
`yellow_tripdata_2021-01.csv.gz` in chunks of 100,000 rows and stops after cleaning.


## Requirements
- Python 3.10+
- pandas

## Run
Keep the data file locally (do not commit it), then run from this folder:

```bash
python -m pip install pandas
python nyc_taxi_cleaning.py --input yellow_tripdata_2021-01.csv.gz
```

## Cleaning policy
- Drop pickup timestamps that are invalid or outside January 2021.
- Drop dropoff timestamps that are invalid or outside January 2021.
- Drop negative fares.
- Retain and flag zero fares, nonpositive distances, and zero passenger counts for review because they may require business context.
- Detect exact duplicate rows during profiling; this dataset contains zero exact duplicate rows.

