from ingest_bronze import main as ingest_bronze
from preprocess_bronze import main as preprocess_bronze

def main():
    ingest_bronze()
    preprocess_bronze()

if __name__ == "__main__":
    main()