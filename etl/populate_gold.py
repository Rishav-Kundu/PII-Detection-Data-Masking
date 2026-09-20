"""
populate_gold.py

Populate the Gold PII catalog from the existing Star Schemas and the
already-trained production PII classifier.

Flow:

    Star schemas
        |
        +--> dim_source_schema
        +--> dim_table
        +--> dim_column
        |
        +--> existing PII classifier
                 |
                 +--> PII type
                 +--> probability
                 +--> confidence
                 |
                 v
             fact_pii_scan

This script does NOT create fake access events. access_audit_logs is
owned by the future access-control/masking layer.

The inference implementation below reproduces the feature construction
used by the supplied production classifier notebook:
    BGE embedding (384)
    + 18 pattern features
    + 34 column-name features
    + 2 PK/FK features
    -> extra_scaler
    -> Logistic Regression
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, text


# ============================================================
# 1. PATHS / CONFIGURATION
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Default location produced by the supplied classifier notebook.
MODEL_DIR = PROJECT_ROOT / "ml" / "pii_classifier"

# Can be overridden:
#   export PII_MODEL_DIR=/path/to/pii_classifier
if os.getenv("PII_MODEL_DIR"):
    MODEL_DIR = Path(os.environ["PII_MODEL_DIR"]).expanduser().resolve()

STAR_SCHEMAS = [
    "star_banking",
    "star_education",
    "star_medical",
    "star_marketing",
]

# Keep this aligned with the classifier's 13 classes.
PII_TYPES = {
    "NON_PII": "Information that is not classified as personally identifiable information",
    "DIRECT_IDENTIFIER": "Information that directly identifies an individual",
    "PERSON_NAME": "First name, last name, or full name",
    "EMAIL": "Email address",
    "PHONE": "Telephone or mobile number",
    "ADDRESS": "Residential or postal address",
    "DATE_OF_BIRTH": "Date of birth",
    "BANK_ACCOUNT_NUMBER": "Bank account number",
    "FINANCIAL_INFORMATION": "Financial or monetary information",
    "HEALTH_INFORMATION": "Health-related personal information",
    "MEDICAL_RECORD_NUMBER": "Medical record identifier",
    "DEMOGRAPHIC_INFORMATION": "Personal demographic information",
    "LOCATION": "Location-related personal information",
}

# Policy layer: the ML model predicts PII type; policy determines sensitivity.
SENSITIVITY_POLICY = {
    "NON_PII": "LOW",
    "DIRECT_IDENTIFIER": "HIGH",
    "EMAIL": "HIGH",
    "PHONE": "HIGH",
    "ADDRESS": "HIGH",
    "DATE_OF_BIRTH": "HIGH",
    "BANK_ACCOUNT_NUMBER": "HIGH",
    "FINANCIAL_INFORMATION": "HIGH",
    "HEALTH_INFORMATION": "HIGH",
    "MEDICAL_RECORD_NUMBER": "HIGH",
    "PERSON_NAME": "MEDIUM",
    "DEMOGRAPHIC_INFORMATION": "MEDIUM",
    "LOCATION": "MEDIUM",
}

# Date dimension range. It only needs to cover scan dates, but a small
# reusable calendar range is convenient.
DATE_START = date(2020, 1, 1)
DATE_END = date(2035, 12, 31)

# Number of non-NULL values sampled from each warehouse column.
# The classifier was trained on 2-5 samples per column (mean=3.03).
# Capping at 5 prevents sample_count feature distortion in StandardScaler.
SAMPLE_SIZE = 5

# Production model version stored in fact_pii_scan.
# If metadata.json contains a version, that value is used instead.
DEFAULT_MODEL_VERSION = "pii-classifier-v1"

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Put your PostgreSQL/Supabase connection "
        "string in the project's .env file."
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


# ============================================================
# 2. LOAD THE PRODUCTION MODEL BUNDLE
# ============================================================

def load_model_bundle() -> dict[str, Any]:
    required = [
        MODEL_DIR / "classifier.joblib",
        MODEL_DIR / "label_encoder.joblib",
        MODEL_DIR / "extra_scaler.joblib",
        MODEL_DIR / "metadata.json",
        MODEL_DIR / "embedding_model",
    ]

    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "The production PII classifier bundle is incomplete.\n"
            "Missing:\n  - " + "\n  - ".join(missing)
        )

    print(f"Loading PII classifier from: {MODEL_DIR}")

    classifier = joblib.load(MODEL_DIR / "classifier.joblib")
    label_encoder = joblib.load(MODEL_DIR / "label_encoder.joblib")
    extra_scaler = joblib.load(MODEL_DIR / "extra_scaler.joblib")

    metadata = json.loads(
        (MODEL_DIR / "metadata.json").read_text(encoding="utf-8")
    )

    bge = SentenceTransformer(str(MODEL_DIR / "embedding_model"))

    print(f"  Model version : {metadata.get('version', DEFAULT_MODEL_VERSION)}")
    print(f"  BGE dimension : {metadata.get('embedding_dimension')}")
    print(f"  Total features: {metadata.get('total_feature_dimension')}")
    print(f"  Classes       : {len(metadata.get('classes', []))}")

    return {
        "classifier": classifier,
        "label_encoder": label_encoder,
        "extra_scaler": extra_scaler,
        "metadata": metadata,
        "bge": bge,
    }


MODEL = load_model_bundle()

CLASSIFIER = MODEL["classifier"]
LABEL_ENCODER = MODEL["label_encoder"]
EXTRA_SCALER = MODEL["extra_scaler"]
MODEL_METADATA = MODEL["metadata"]
BGE = MODEL["bge"]

MODEL_VERSION = MODEL_METADATA.get(
    "version",
    DEFAULT_MODEL_VERSION,
)

COLUMN_KEYWORDS = MODEL_METADATA["column_name_keywords"]
PATTERN_FEATURE_NAMES = MODEL_METADATA["pattern_feature_names"]
EXTRA_FEATURE_NAMES = MODEL_METADATA["extra_feature_names"]

EXPECTED_EMBEDDING_DIM = int(
    MODEL_METADATA["embedding_dimension"]
)
EXPECTED_EXTRA_DIM = int(
    MODEL_METADATA["extra_feature_dimension"]
)
EXPECTED_TOTAL_DIM = int(
    MODEL_METADATA["total_feature_dimension"]
)

MODEL_CLASSES = set(
    LABEL_ENCODER.classes_.tolist()
)

unknown_model_classes = MODEL_CLASSES - set(PII_TYPES)
if unknown_model_classes:
    raise ValueError(
        f"Classifier contains classes not present in Gold taxonomy: "
        f"{sorted(unknown_model_classes)}"
    )


# ============================================================
# 3. EXACT PATTERN FEATURES FROM THE CLASSIFIER
# ============================================================

EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)

PHONE_RE = re.compile(
    r"^(?:\+91[- ]?|0)?[6-9]\d{9}$"
)

DATE_RE = re.compile(
    r"^(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})$"
)

CREDIT_CARD_RE = re.compile(
    r"^(?:\d[ -]?){13,19}$"
)

BANK_ACCOUNT_RE = re.compile(
    r"^\d{8,18}$"
)

MEDICAL_RECORD_RE = re.compile(
    r"^(?:MRN[-_ ]?)?[A-Za-z0-9]{5,20}$",
    re.I,
)

ALPHA_RE = re.compile(
    r"^[A-Za-z .\-']+$"
)

NUMERIC_RE = re.compile(
    r"^[-+]?\d+(?:\.\d+)?$"
)

ALPHANUMERIC_RE = re.compile(
    r"^[A-Za-z0-9]+$"
)


def split_sample_values(value: Any) -> list[str]:
    """Exactly match the supplied notebook's sample-value parsing."""
    if value is None:
        return []

    raw = str(value).strip()

    if not raw or raw.upper() == "NULL":
        return []

    return [x.strip() for x in raw.split("|") if x.strip()]


def safe_ratio(matches: int, total: int) -> float:
    return matches / total if total else 0.0


def profile_samples(sample_values: str) -> np.ndarray:
    """
    Reproduce the 18 pattern features from the supplied classifier.
    """
    values = split_sample_values(sample_values)
    n = len(values)

    if n == 0:
        return np.zeros(18, dtype=np.float32)

    lengths = np.array(
        [len(v) for v in values],
        dtype=np.float32,
    )

    email_ratio = safe_ratio(
        sum(bool(EMAIL_RE.fullmatch(v)) for v in values),
        n,
    )

    phone_ratio = safe_ratio(
        sum(bool(PHONE_RE.fullmatch(v)) for v in values),
        n,
    )

    date_ratio = safe_ratio(
        sum(bool(DATE_RE.fullmatch(v)) for v in values),
        n,
    )

    credit_card_ratio = safe_ratio(
        sum(
            bool(CREDIT_CARD_RE.fullmatch(v.replace(" ", "")))
            for v in values
        ),
        n,
    )

    bank_account_ratio = safe_ratio(
        sum(bool(BANK_ACCOUNT_RE.fullmatch(v)) for v in values),
        n,
    )

    medical_record_ratio = safe_ratio(
        sum(bool(MEDICAL_RECORD_RE.fullmatch(v)) for v in values),
        n,
    )

    numeric_ratio = safe_ratio(
        sum(bool(NUMERIC_RE.fullmatch(v)) for v in values),
        n,
    )

    alphabetic_ratio = safe_ratio(
        sum(bool(ALPHA_RE.fullmatch(v)) for v in values),
        n,
    )

    alphanumeric_ratio = safe_ratio(
        sum(bool(ALPHANUMERIC_RE.fullmatch(v)) for v in values),
        n,
    )

    unique_ratio = (
        len(set(v.lower() for v in values)) / n
    )

    return np.array(
        [
            email_ratio,
            phone_ratio,
            date_ratio,
            credit_card_ratio,
            bank_account_ratio,
            medical_record_ratio,
            numeric_ratio,
            alphabetic_ratio,
            alphanumeric_ratio,
            unique_ratio,
            float(lengths.mean()),
            float(lengths.min()),
            float(lengths.max()),
            float(n == 0),
            float(len(values)),
            float(np.std(lengths)),
            float(np.mean([len(v.split()) for v in values])),
            float(
                np.mean(
                    [
                        any(c.isdigit() for c in v)
                        for v in values
                    ]
                )
            ),
        ],
        dtype=np.float32,
    )


def binary_feature(value: Any) -> int:
    return int(
        str(value).strip().lower()
        in {"true", "1", "yes", "y"}
    )


def column_name_features(column_name: str) -> np.ndarray:
    """
    Reproduce the exact column keyword feature construction
    from the supplied classifier.
    """
    name = str(column_name).lower().replace("-", "_")

    return np.array(
        [
            float(keyword in name)
            for keyword in COLUMN_KEYWORDS
        ],
        dtype=np.float32,
    )


# ============================================================
# 4. DATABASE HELPERS
# ============================================================

def fetch_all(query: str, params: dict[str, Any] | None = None):
    with engine.connect() as connection:
        result = connection.execute(
            text(query),
            params or {},
        )
        return [dict(row._mapping) for row in result]


def fetch_one(query: str, params: dict[str, Any] | None = None):
    with engine.connect() as connection:
        result = connection.execute(
            text(query),
            params or {},
        )
        row = result.fetchone()
        return None if row is None else dict(row._mapping)


def execute(query: str, params: dict[str, Any] | None = None):
    with engine.begin() as connection:
        connection.execute(
            text(query),
            params or {},
        )


def quote_identifier(identifier: str) -> str:
    """
    Quote a PostgreSQL identifier.
    Identifiers used here are first verified through
    information_schema, and double quotes are escaped as an
    additional safeguard.
    """
    return '"' + identifier.replace('"', '""') + '"'


# ============================================================
# 5. DISCOVER STAR-SCHEMA METADATA
# ============================================================

def populate_source_schemas():
    print("\n[1] Populating gold.dim_source_schema")

    for schema_name in STAR_SCHEMAS:
        execute(
            """
            INSERT INTO gold.dim_source_schema
                (schema_name, description)
            VALUES
                (:schema_name, :description)
            ON CONFLICT (schema_name)
            DO NOTHING
            """,
            {
                "schema_name": schema_name,
                "description": (
                    f"{schema_name.replace('star_', '').title()} "
                    "domain star schema"
                ),
            },
        )

        print(f"  ✓ {schema_name}")


def populate_tables():
    print("\n[2] Populating gold.dim_table")

    execute(
        """
        INSERT INTO gold.dim_table
            (source_schema_key, table_name, description)
        SELECT
            s.source_schema_key,
            t.table_name,
            'Warehouse table in ' || s.schema_name
        FROM gold.dim_source_schema s
        JOIN information_schema.tables t
            ON t.table_schema = s.schema_name
        WHERE
            s.schema_name = ANY(:schemas)
            AND t.table_type = 'BASE TABLE'
        ON CONFLICT (source_schema_key, table_name)
        DO NOTHING
        """,
        {"schemas": STAR_SCHEMAS},
    )

    rows = fetch_all(
        """
        SELECT
            s.schema_name,
            t.table_name
        FROM gold.dim_source_schema s
        JOIN gold.dim_table t
            ON t.source_schema_key = s.source_schema_key
        WHERE s.schema_name = ANY(:schemas)
        ORDER BY s.schema_name, t.table_name
        """,
        {"schemas": STAR_SCHEMAS},
    )

    for row in rows:
        print(
            f"  ✓ {row['schema_name']}.{row['table_name']}"
        )


def populate_columns():
    print("\n[3] Populating gold.dim_column")

    execute(
        """
        INSERT INTO gold.dim_column
            (
                table_key,
                column_name,
                data_type,
                nullable,
                ordinal_position
            )
        SELECT
            t.table_key,
            c.column_name,
            c.data_type,
            CASE
                WHEN c.is_nullable = 'YES'
                THEN TRUE
                ELSE FALSE
            END,
            c.ordinal_position
        FROM gold.dim_table t
        JOIN gold.dim_source_schema s
            ON s.source_schema_key = t.source_schema_key
        JOIN information_schema.columns c
            ON c.table_schema = s.schema_name
            AND c.table_name = t.table_name
        WHERE s.schema_name = ANY(:schemas)
        ON CONFLICT (table_key, column_name)
        DO NOTHING
        """,
        {"schemas": STAR_SCHEMAS},
    )

    result = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM gold.dim_column c
        JOIN gold.dim_table t
            ON t.table_key = c.table_key
        JOIN gold.dim_source_schema s
            ON s.source_schema_key = t.source_schema_key
        WHERE s.schema_name = ANY(:schemas)
        """,
        {"schemas": STAR_SCHEMAS},
    )

    print(f"  ✓ {result['count']} columns catalogued")


# ============================================================
# 6. SEED STATIC GOLD DIMENSIONS
# ============================================================

def populate_pii_types():
    print("\n[4] Populating gold.dim_pii_type")

    for pii_type, description in PII_TYPES.items():
        execute(
            """
            INSERT INTO gold.dim_pii_type
                (pii_type, description)
            VALUES
                (:pii_type, :description)
            ON CONFLICT (pii_type)
            DO NOTHING
            """,
            {
                "pii_type": pii_type,
                "description": description,
            },
        )

    print(f"  ✓ {len(PII_TYPES)} PII types")


def populate_sensitivity():
    print("\n[5] Populating gold.dim_sensitivity")

    descriptions = {
        "HIGH":
            "Highly sensitive personal information requiring strong protection",
        "MEDIUM":
            "Moderately sensitive personal information",
        "LOW":
            "Lower sensitivity information that may still require governance",
    }

    for level, description in descriptions.items():
        execute(
            """
            INSERT INTO gold.dim_sensitivity
                (sensitivity_level, description)
            VALUES
                (
                    CAST(:level AS gold.sensitivity_types),
                    :description
                )
            ON CONFLICT (sensitivity_level)
            DO NOTHING
            """,
            {
                "level": level,
                "description": description,
            },
        )

    print("  ✓ HIGH / MEDIUM / LOW")


def populate_dates():
    print("\n[6] Populating gold.dim_date")

    execute(
        """
        INSERT INTO gold.dim_date (
            date_key,
            full_date,
            day,
            month,
            month_name,
            quarter,
            year,
            is_weekend
        )
        SELECT
            TO_CHAR(d, 'YYYYMMDD')::INTEGER AS date_key,
            d::DATE AS full_date,
            EXTRACT(DAY FROM d)::INTEGER AS day,
            EXTRACT(MONTH FROM d)::INTEGER AS month,
            TO_CHAR(d, 'FMMonth') AS month_name,
            EXTRACT(QUARTER FROM d)::INTEGER AS quarter,
            EXTRACT(YEAR FROM d)::INTEGER AS year,
            EXTRACT(ISODOW FROM d) IN (6, 7) AS is_weekend
        FROM generate_series(
            CAST(:start_date AS DATE),
            CAST(:end_date AS DATE),
            INTERVAL '1 day'
        ) AS g(d)
        ON CONFLICT (date_key) DO NOTHING;
        """,
        {
            "start_date": DATE_START,
            "end_date": DATE_END,
        },
    )

    print(
        f"  ✓ {DATE_START} → {DATE_END}"
    )


# ============================================================
# 7. COLUMN INVENTORY FOR CLASSIFICATION
# ============================================================

def get_column_inventory() -> list[dict[str, Any]]:
    """
    Return the columns that should be scanned.

    table_type is derived from the actual star-schema table name
    because the production classifier was trained with DIMENSION/FACT
    table-type information.
    """
    return fetch_all(
        """
        SELECT
            s.source_schema_key,
            s.schema_name,

            t.table_key,
            t.table_name,

            c.column_key,
            c.column_name,
            c.data_type,
            c.nullable,
            c.ordinal_position,

            CASE
                WHEN LOWER(t.table_name) LIKE 'fact_%'
                THEN 'FACT'
                WHEN LOWER(t.table_name) LIKE 'dim_%'
                THEN 'DIMENSION'
                ELSE 'TABLE'
            END AS table_type,

            EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                    AND tc.table_name = kcu.table_name
                WHERE
                    tc.constraint_type = 'PRIMARY KEY'
                    AND tc.table_schema = s.schema_name
                    AND tc.table_name = t.table_name
                    AND kcu.column_name = c.column_name
            ) AS is_primary_key,

            EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                    AND tc.table_name = kcu.table_name
                WHERE
                    tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = s.schema_name
                    AND tc.table_name = t.table_name
                    AND kcu.column_name = c.column_name
            ) AS is_foreign_key

        FROM gold.dim_source_schema s
        JOIN gold.dim_table t
            ON t.source_schema_key = s.source_schema_key
        JOIN gold.dim_column c
            ON c.table_key = t.table_key

        WHERE s.schema_name = ANY(:schemas)

        ORDER BY
            s.schema_name,
            t.table_name,
            c.ordinal_position
        """,
        {"schemas": STAR_SCHEMAS},
    )


# ============================================================
# 8. READ SAMPLE VALUES FROM STAR SCHEMA
# ============================================================

def get_sample_values(
    schema_name: str,
    table_name: str,
    column_name: str,
) -> list[str]:

    # Verify the identifier exists before constructing dynamic SQL.
    exists = fetch_one(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE
            table_schema = :schema_name
            AND table_name = :table_name
            AND column_name = :column_name
        """,
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "column_name": column_name,
        },
    )

    if exists is None:
        raise ValueError(
            f"Column does not exist: "
            f"{schema_name}.{table_name}.{column_name}"
        )

    schema_q = quote_identifier(schema_name)
    table_q = quote_identifier(table_name)
    column_q = quote_identifier(column_name)

    query = f"""
        SELECT {column_q} AS value
        FROM {schema_q}.{table_q}
        WHERE {column_q} IS NOT NULL
        LIMIT :sample_size
    """

    rows = fetch_all(
        query,
        {"sample_size": SAMPLE_SIZE},
    )

    return [
        str(row["value"]).strip()
        for row in rows
        if row["value"] is not None
    ]


def count_records(
    schema_name: str,
    table_name: str,
) -> int:

    # Table name is discovered from information_schema before use.
    exists = fetch_one(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE
            table_schema = :schema_name
            AND table_name = :table_name
            AND table_type = 'BASE TABLE'
        """,
        {
            "schema_name": schema_name,
            "table_name": table_name,
        },
    )

    if exists is None:
        raise ValueError(
            f"Table does not exist: "
            f"{schema_name}.{table_name}"
        )

    query = f"""
        SELECT COUNT(*) AS count
        FROM {quote_identifier(schema_name)}.
             {quote_identifier(table_name)}
    """

    result = fetch_one(query)

    return int(result["count"])


# ============================================================
# 9. BUILD THE EXACT BGE INPUT
# ============================================================

def clean_value(value: Any) -> str:
    if value is None:
        return "NULL"
    return str(value).strip()


def build_semantic_text(
    domain: str,
    table_name: str,
    table_type: str,
    column_name: str,
    data_type: str,
    sample_values: list[str],
) -> str:
    """
    Exact structure used by the supplied classifier notebook.
    """
    sample_string = "|".join(sample_values)

    return (
        f"Domain: {clean_value(domain)}. "
        f"Table: {clean_value(table_name)}. "
        f"Table type: {clean_value(table_type)}. "
        f"Column: {clean_value(column_name)}. "
        f"Data type: {clean_value(data_type)}. "
        f"Sample values: {clean_value(sample_string)}."
    )


def schema_to_domain(schema_name: str) -> str:
    return schema_name.replace(
        "star_", ""
    ).title()


# ============================================================
# 10. CLASSIFY ONE COLUMN
# ============================================================

def classify_column(
    column: dict[str, Any],
    sample_values: list[str],
) -> dict[str, Any]:

    # Cap sample values to at most 5 to match the classifier's training distribution
    # (training dataset had 2-5 sample values per row, mean=3.03).
    capped_samples = sample_values[:5]
    sample_string = "|".join(capped_samples)

    semantic_text = build_semantic_text(
        domain=schema_to_domain(column["schema_name"]),
        table_name=column["table_name"],
        table_type=column["table_type"],
        column_name=column["column_name"],
        data_type=column["data_type"],
        sample_values=capped_samples,
    )

    # BGE embedding — same settings as training notebook.
    embedding = BGE.encode(
        [semantic_text],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype(np.float32)

    if embedding.shape[1] != EXPECTED_EMBEDDING_DIM:
        raise RuntimeError(
            f"BGE dimension mismatch: got {embedding.shape[1]}, "
            f"expected {EXPECTED_EMBEDDING_DIM}"
        )

    # Exact 18 pattern features.
    pattern_features = profile_samples(
        sample_string
    ).reshape(1, -1)

    # Exact column-name keyword features.
    name_features = column_name_features(
        column["column_name"]
    ).reshape(1, -1)

    # Exact PK/FK features.
    metadata_features = np.array(
        [
            [
                binary_feature(column["is_primary_key"]),
                binary_feature(column["is_foreign_key"]),
            ]
        ],
        dtype=np.float32,
    )

    # Exact training-time feature order:
    # patterns + column-name + PK/FK.
    extra_features = np.hstack(
        [
            pattern_features,
            name_features,
            metadata_features,
        ]
    ).astype(np.float32)

    if extra_features.shape[1] != EXPECTED_EXTRA_DIM:
        raise RuntimeError(
            f"Extra feature dimension mismatch: "
            f"got {extra_features.shape[1]}, "
            f"expected {EXPECTED_EXTRA_DIM}"
        )

        # The final production model was trained with:
    #
    # final_extra_scaler.fit_transform(extra_features)
    # X_final = [BGE embedding | scaled extra features]
    #
    scaled_extra = EXTRA_SCALER.transform(
        extra_features
    ).astype(np.float32)

    X = np.hstack(
        [
            embedding,
            scaled_extra,
        ]
    ).astype(np.float32)

    if X.shape[1] != EXPECTED_TOTAL_DIM:
        raise RuntimeError(
            f"Final feature dimension mismatch: "
            f"got {X.shape[1]}, "
            f"expected {EXPECTED_TOTAL_DIM}"
        )

    
    

    # Production Logistic Regression.
    predicted_encoded = CLASSIFIER.predict(X)[0]
    probabilities = CLASSIFIER.predict_proba(X)[0]

    predicted_label = LABEL_ENCODER.inverse_transform(
        [predicted_encoded]
    )[0]

    probability = float(
        probabilities[int(predicted_encoded)]
    )

    final_confidence = float(
        probabilities.max()
    )

    if predicted_label not in PII_TYPES:
        raise ValueError(
            f"Unknown classifier label: {predicted_label}"
        )
    


    #DEBUG STATUS CODE:


    print("\n========== CLASSIFIER DEBUG ==========")
    print("semantic_text:")
    print(semantic_text)

    print("\npattern_features:")
    print(pattern_features)

    print("\nname_features:")
    print(name_features)

    print("\nmetadata_features:")
    print(metadata_features)

    print("\nembedding:")
    print(
        "shape =", embedding.shape,
        "mean =", embedding.mean(),
        "std =", embedding.std()
    )

    print("\nextra:")
    print(
        "shape =", extra_features.shape,
        "mean =", extra_features.mean(),
        "std =", extra_features.std()
    )

    print("\nX:")
    print(
        "shape =", X.shape,
        "mean =", X.mean(),
        "std =", X.std()
    )

    print("\nMODEL:")
    print("classifier classes =", CLASSIFIER.classes_)
    print("encoder classes    =", LABEL_ENCODER.classes_)

    print("\nPROBABILITIES:")
    print(CLASSIFIER.predict_proba(X)[0])

    print("predicted encoded =", predicted_encoded)
    print("predicted label   =", predicted_label)
    print("======================================")



    return {
        "pii_type": predicted_label,
        "pii_detected": predicted_label != "NON_PII",
        "ml_probability": probability,
        "final_confidence": final_confidence,
    }


# ============================================================
# 11. RESOLVE GOLD KEYS
# ============================================================

def resolve_gold_keys(
    schema_name: str,
    table_name: str,
    column_name: str,
    pii_type: str,
) -> dict[str, Any]:

    sensitivity = SENSITIVITY_POLICY.get(pii_type)

    if sensitivity is None:
        raise ValueError(
            f"No sensitivity policy exists for {pii_type}"
        )

    row = fetch_one(
        """
        SELECT
            s.source_schema_key,
            t.table_key,
            c.column_key,
            p.pii_type_key,
            se.sensitivity_key

        FROM gold.dim_source_schema s

        JOIN gold.dim_table t
            ON t.source_schema_key = s.source_schema_key
            AND t.table_name = :table_name

        JOIN gold.dim_column c
            ON c.table_key = t.table_key
            AND c.column_name = :column_name

        JOIN gold.dim_pii_type p
            ON p.pii_type = :pii_type

        JOIN gold.dim_sensitivity se
            ON se.sensitivity_level =
                CAST(
                    :sensitivity
                    AS gold.sensitivity_types
                )

        WHERE s.schema_name = :schema_name
        """,
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "column_name": column_name,
            "pii_type": pii_type,
            "sensitivity": sensitivity,
        },
    )

    if row is None:
        raise RuntimeError(
            "Could not resolve Gold keys for "
            f"{schema_name}.{table_name}.{column_name}"
        )

    return row


# ============================================================
# 12. INSERT PII SCAN FACT
# ============================================================

def insert_pii_scan(
    keys: dict[str, Any],
    prediction: dict[str, Any],
    records_scanned: int,
):
    """
    Insert the column-level scan result.

    pii_records_detected is intentionally NULL in this first
    implementation because the classifier is a COLUMN-LEVEL
    classifier, not a row-level PII detector. We must not claim
    an exact row count that the model did not calculate.
    """

    today = date.today()
    date_key = int(today.strftime("%Y%m%d"))

    execute(
        """
        INSERT INTO gold.fact_pii_scan
        (
            source_schema_key,
            table_key,
            column_key,
            pii_type_key,
            sensitivity_key,
            date_key,
            scan_timestamp,
            pii_detected,
            ml_probability,
            final_confidence,
            model_version,
            masking_enabled,
            masking_technique,
            records_scanned,
            pii_records_detected
        )
        VALUES
        (
            :source_schema_key,
            :table_key,
            :column_key,
            :pii_type_key,
            :sensitivity_key,
            :date_key,
            CURRENT_TIMESTAMP,
            :pii_detected,
            :ml_probability,
            :final_confidence,
            :model_version,
            FALSE,
            NULL,
            :records_scanned,
            NULL
        )
        """,
        {
            "source_schema_key": keys["source_schema_key"],
            "table_key": keys["table_key"],
            "column_key": keys["column_key"],
            "pii_type_key": keys["pii_type_key"],
            "sensitivity_key": keys["sensitivity_key"],
            "date_key": date_key,
            "pii_detected": prediction["pii_detected"],
            "ml_probability": prediction["ml_probability"],
            "final_confidence": prediction["final_confidence"],
            "model_version": MODEL_VERSION,
            "records_scanned": records_scanned,
        },
    )


# ============================================================
# 13. SCAN ALL STAR-SCHEMA COLUMNS
# ============================================================

def run_pii_scan():
    print("\n[7] Running the existing PII classifier")

    columns = get_column_inventory()

    print(
        f"  Columns to scan: {len(columns)}"
    )

    successful = 0
    failed = 0

    for column in columns:

        schema_name = column["schema_name"]
        table_name = column["table_name"]
        column_name = column["column_name"]

        label = (
            f"{schema_name}.{table_name}.{column_name}"
        )

        print(f"\n  → {label}")

        try:
            samples = get_sample_values(
                schema_name=schema_name,
                table_name=table_name,
                column_name=column_name,
            )

            records_scanned = count_records(
                schema_name=schema_name,
                table_name=table_name,
            )

            prediction = classify_column(
                column=column,
                sample_values=samples,
            )

            keys = resolve_gold_keys(
                schema_name=schema_name,
                table_name=table_name,
                column_name=column_name,
                pii_type=prediction["pii_type"],
            )

            insert_pii_scan(
                keys=keys,
                prediction=prediction,
                records_scanned=records_scanned,
            )

            print(
                f"     {prediction['pii_type']}"
                f" | detected={prediction['pii_detected']}"
                f" | confidence={prediction['final_confidence']:.4f}"
                f" | rows={records_scanned}"
            )

            successful += 1

        except Exception as exc:
            failed += 1
            print(f"     ✗ FAILED: {exc}")

    print("\n----------------------------------------")
    print("PII scan finished")
    print(f"Successful: {successful}")
    print(f"Failed:     {failed}")
    print("----------------------------------------")


# ============================================================
# 14. VALIDATE GOLD POPULATION
# ============================================================

def validate_gold():
    print("\n[8] Validating Gold layer")

    checks = [
        (
            "dim_source_schema",
            """
            SELECT COUNT(*) AS count
            FROM gold.dim_source_schema
            """
        ),
        (
            "dim_table",
            """
            SELECT COUNT(*) AS count
            FROM gold.dim_table
            """
        ),
        (
            "dim_column",
            """
            SELECT COUNT(*) AS count
            FROM gold.dim_column
            """
        ),
        (
            "dim_pii_type",
            """
            SELECT COUNT(*) AS count
            FROM gold.dim_pii_type
            """
        ),
        (
            "dim_sensitivity",
            """
            SELECT COUNT(*) AS count
            FROM gold.dim_sensitivity
            """
        ),
        (
            "dim_date",
            """
            SELECT COUNT(*) AS count
            FROM gold.dim_date
            """
        ),
        (
            "fact_pii_scan",
            """
            SELECT COUNT(*) AS count
            FROM gold.fact_pii_scan
            """
        ),
    ]

    for name, query in checks:
        result = fetch_one(query)
        print(
            f"  {name:25s}: {result['count']}"
        )


# ============================================================
# 15. MAIN
# ============================================================

def main():

    print("=" * 65)
    print("PII DETECTION — GOLD LAYER POPULATION")
    print("=" * 65)

    print("\nDatabase connection test...")

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    print("✓ PostgreSQL connection successful")

    print("\nStar schemas:")
    for schema in STAR_SCHEMAS:
        print(f"  - {schema}")

    populate_source_schemas()
    populate_tables()
    populate_columns()

    populate_pii_types()
    populate_sensitivity()
    populate_dates()

    run_pii_scan()

    validate_gold()

    print("\n" + "=" * 65)
    print("GOLD POPULATION COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    main()
