PII Detection & Data Masking

A compliance-oriented data warehouse prototype for discovering, classifying, cataloging, and masking Personally Identifiable Information (PII) across Banking, Education, Medical, and Marketing domains.

Hackathon Prototype: All datasets in this repository are synthetic and intended for development, testing, demonstration, and educational purposes. They do not contain real customer, student, patient, or financial information.

📌 Overview

Organizations store sensitive information across multiple systems such as banking, education, healthcare, and marketing. Before sensitive information can be reliably detected and protected, incoming data needs to be preserved, cleaned, standardized, and organized into an analytical structure.

This project follows a layered data warehouse architecture:

                         CSV / Source Data
                                │
                                ▼
                     ┌─────────────────────┐
                     │    BRONZE LAYER     │
                     │   Raw / Append-only │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │    SILVER LAYER     │
                     │ Cleaned / Typed /   │
                     │ Validated / Persist.│
                     └──────────┬──────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
   │   Banking   │      │  Education  │      │   Medical   │
   │ Star Schema │      │ Star Schema │      │ Star Schema │
   └─────────────┘      └─────────────┘      └─────────────┘
                                │
                                ▼
                       ┌────────────────┐
                       │    Marketing   │
                       │  Star Schema   │
                       └───────┬────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ GOLD / PII ANALYSIS  │
                    │ Profiling + ML + PII │
                    │ Catalog + Masking    │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ API + RBAC +         │
                    │ Dashboards / Reports │
                    └──────────────────────┘

The four business domains remain logically separate in their Star schemas. They can later feed a common Gold layer without being merged into one large source table.

🎯 Objectives

The project is designed to:

Preserve raw incoming source data.

Clean and standardize source records.

Detect invalid and duplicate records during Silver processing.

Maintain Silver data permanently rather than rebuilding it on every run.

Organize cleaned data into analytical Star schemas.

Profile data and identify potential PII.

Combine deterministic pattern detection with AI/ML-assisted classification.

Maintain a centralized PII catalog.

Apply role-based masking policies.

Provide APIs and dashboards for controlled access and reporting.

Support auditing and governance of sensitive information.

🏗️ Data Warehouse Architecture

1. Bronze Layer

The Bronze layer is the raw landing zone.

Bronze Principles

Bronze performs no row-level business validation.

It:

Accepts every source row.

Preserves incoming values as closely as possible.

Does not clean field values.

Does not reject invalid records.

Does not deduplicate records.

Is append-only.

Adds technical ingestion metadata.

The purpose is to preserve the original source information so downstream processing can be reproduced and audited.

Bronze Tables

bronze.banking
bronze.education
bronze.medical
bronze.marketing
bronze._ingestion_manifest

Technical metadata includes:

_bronze_id

_source_file

_ingestion_batch_id

_ingested_at

The ingestion manifest tracks previously ingested file signatures and prevents accidental re-ingestion of the same physical file.

2. Silver Layer

The Silver layer contains cleaned, standardized, typed, and persistent data.

Bronze → Silver Flow

Bronze Record
     │
     ▼
Read raw values
     │
     ▼
Normalize / Clean
     │
     ▼
Convert data types
     │
     ▼
Validate critical fields
     │
     ├───────────────┐
     ▼               ▼
Valid record     Rejected record
     │               │
     ▼               │
Silver table         │
                     │
          Bronze record remains
          available for audit

Silver Persistence

Silver is incremental and persistent.

A Bronze record that has already been processed is not processed again based on its _bronze_id.

Existing Silver records are not truncated when the ETL is rerun.

Therefore:

New Bronze records are processed.

Previously processed Bronze records are skipped.

Existing Silver records remain unchanged.

Bronze records are never deleted by the Bronze → Silver ETL.

Critical-Field Rules

A row is rejected when a critical condition is encountered, such as:

Invalid or missing primary key.

Duplicate primary key against existing Silver data.

Missing required first_name.

Exact or normalized duplicate record.

Non-critical invalid values do not cause the entire row to be rejected.

Instead, the affected field is converted to database NULL.

Examples include invalid:

Email addresses.

Phone numbers.

Dates.

Numeric values.

Categories.

Optional dimension values.

Important Domain Rule

Negative banking balances are allowed.

A negative balance can represent a legitimate overdraft or similar account state, so the ETL does not automatically treat a negative balance as invalid.

⭐ Star Schemas

After Silver processing, each business domain is transformed into its own Star schema.

Silver Banking    → star_banking
Silver Education  → star_education
Silver Medical    → star_medical
Silver Marketing  → star_marketing

The four domains are equal analytical domains.

The Star ETLs are incremental and idempotent, so rerunning them does not create duplicate fact records for already processed Silver records.

🏦 Banking Star Schema

Dimension Tables

star_banking.dim_customer
star_banking.dim_account
star_banking.dim_location

Fact Table

star_banking.fact_account

The fact table represents an account-level Silver record.

Optional account information can remain NULL when the corresponding Silver data is unavailable.

🎓 Education Star Schema

Dimension Tables

star_education.dim_student
star_education.dim_course
star_education.dim_department
star_education.dim_location
star_education.dim_date

Fact Table

star_education.fact_enrollment

The fact table connects students with course, department, location, enrollment date, and percentage information.

The date dimension contains standard analytical attributes such as:

Date key

Full date

Day

Day name

Week

Month

Month name

Quarter

Year

Weekend indicator

🏥 Medical Star Schema

Dimension Tables

star_medical.dim_patient
star_medical.dim_doctor
star_medical.dim_diagnosis
star_medical.dim_location
star_medical.dim_date

Fact Table

star_medical.fact_admission

The fact table represents an admission record and links the patient to doctor, diagnosis, location, and admission date.

Optional information such as doctor or admission date can remain NULL when the corresponding Silver value is unavailable.

📢 Marketing Star Schema

Dimension Tables

star_marketing.dim_customer
star_marketing.dim_campaign
star_marketing.dim_channel
star_marketing.dim_location
star_marketing.dim_date

Fact Table

star_marketing.fact_campaign

The fact table represents a campaign record from Silver and links it to customer, campaign, channel, location, and campaign date.

No unsupported response or conversion metric is invented from the source data.

🔄 ETL Pipeline

CSV → Bronze

Run:

python -m etl.ingest_bronze

The ingestion process:

Scans data/incoming/ for CSV files.

Automatically determines the business domain from CSV structure.

Reads source values as strings.

Normalizes column names only.

Adds technical metadata.

Appends every source row to the appropriate Bronze table.

Registers the file in the ingestion manifest.

Filenames are not hardcoded.

A supported CSV can be routed automatically according to its column structure.

Bronze → Silver

Run:

python -m etl.preprocess_bronze

The process:

Reads Bronze records in _bronze_id order.

Skips records already represented in Silver.

Cleans and standardizes field values.

Converts values into appropriate database types.

Validates critical fields.

Rejects records that violate critical rules.

Converts invalid non-critical fields to NULL.

Inserts valid records into Silver.

Leaves Bronze unchanged.

Silver → Star

Run the required domain ETLs:

python -m etl.star_banking
python -m etl.star_education
python -m etl.star_medical
python -m etl.star_marketing

Each Star ETL loads dimensions and facts incrementally and uses the source Bronze identifier to prevent duplicate fact records.

🧪 Test Datasets

The repository contains both clean reference datasets and deliberately dirty datasets.

Clean Datasets

data/raw_banking.csv
data/raw_education.csv
data/raw_medical.csv
data/raw_marketing.csv

Each contains 25 synthetic records.

Dirty Datasets

data/dirty_banking.csv
data/dirty_education.csv
data/dirty_medical.csv
data/dirty_marketing.csv

The dirty datasets contain test cases such as:

Missing values.

Invalid email addresses.

Invalid phone numbers.

Invalid dates.

Invalid categorical values.

Invalid numeric values.

Duplicate primary keys.

Missing first names.

Duplicate records.

Negative values where appropriate.

Other malformed source values.

Reference datasets remain under data/ so collaborators can access them from GitHub.

The actual ingestion queue is:

data/incoming/

The data/incoming/ directory is ignored by Git.

Example

cp data/dirty_banking.csv data/incoming/
python -m etl.ingest_bronze

📊 Current Pipeline Validation

The current synthetic environment has been used to validate the complete Bronze → Silver → Star pipeline.

Clean-Data Load

Domain

Bronze

Silver

Banking

25

25

Education

25

25

Medical

25

25

Marketing

25

25

Total

100

100

Dirty-Data Test

After loading the dirty datasets:

Domain

Bronze

Silver Retained

Rejected

Banking

50

48

2

Education

50

48

2

Medical

50

48

2

Marketing

50

48

2

Total

200

192

8

The rejected records in the current synthetic test were due to critical-field conditions such as missing first names and duplicate primary keys.

The test also confirmed that non-critical invalid values remain preserved in Bronze while becoming NULL in Silver.

Star-Schema Validation

All four Star ETLs were executed with the dirty Silver data and then rerun.

The second execution did not increase the existing fact counts or create duplicate fact records, confirming idempotent behavior for the tested dataset.

🤖 PII Discovery & AI/ML Layer

The PII analysis layer is designed to operate after the cleaned and structured warehouse data is available.

Planned Workflow

Star Schemas
     │
     ▼
Data Profiling
     │
     ▼
Pattern Detection
     │
     ▼
Feature Extraction
     │
     ▼
ML / Semantic Analysis
     │
     ▼
PII Classification
     │
     ▼
Gold Layer
     │
     ├── PII Results
     ├── Sensitivity
     ├── Confidence
     └── Detection Metadata

Potential profiling signals include:

Column name.

Data type.

Null percentage.

Uniqueness.

Average value length.

Pattern-match percentage.

Table/domain context.

Semantic context.

Deterministic pattern detection can identify formats such as:

Email addresses.

Indian phone numbers.

Dates.

Account numbers.

Medical record numbers.

ML-assisted classification can subsequently use engineered features and semantic information to classify potential PII.

The final implementation and evaluation of this layer are part of ongoing development.

📚 Gold Layer & PII Catalog

The planned Gold layer will contain derived analytical and PII-related outputs rather than replacing the four domain-specific Star schemas.

A possible logical organization is:

gold.banking_analysis
gold.education_analysis
gold.medical_analysis
gold.marketing_analysis
gold.pii_results
gold.pii_catalog
gold.masking_metadata
gold.ml_results

Typical PII catalog information may include:

Attribute

Description

Domain

Business domain

Schema

Source warehouse schema

Table

Source table

Column

Source column

PII Type

Detected PII category

Sensitivity

Sensitivity classification

Detection Method

Pattern / ML / Combined

Confidence

Classification confidence

Masking Status

Whether a masking policy applies

🔐 Dynamic Data Masking

The planned masking layer protects sensitive information according to the authenticated user's role.

                    User
                      │
                      ▼
                    RBAC
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
       Admin       Analyst    Unauthorized
          │           │           │
          ▼           ▼           ▼
     Authorized      Masked       Denied
       Data          Data         Access

Email

Original:
aarav.sharma@example.com

Masked:
a****@example.com

Phone

Original:
9876543210

Masked:
******3210

Account Number

Original:
123456789012

Masked:
********9012

The exact masking behavior will be determined by the final PII classification and access-control implementation.

👥 Role-Based Access Control

The planned access model uses role-based authorization.

Role

Intended Access

Administrator

Authorized access to sensitive/unmasked data

Analyst

Masked data according to policy

Unauthorized User

Access denied

Authorization should ultimately be enforced by the backend/API rather than relying only on frontend visibility.

📈 Dashboard & Reporting

The planned dashboard layer will provide visibility into PII discovery and masking.

PII Inventory

Total detected PII fields.

PII by domain.

PII by table.

PII by column.

PII categories.

Sensitivity Analysis

Distribution of sensitive fields.

Sensitivity by domain.

Sensitivity by PII category.

Masking Coverage

Sensitive Fields
       vs.
Masked Fields

Access Audit

Potential audit information:

User/role.

Accessed resource.

Timestamp.

Action.

Access result.

🛠️ Technology Stack

Component

Technology

Programming Language

Python

Database

PostgreSQL

Data Warehouse

Supabase PostgreSQL

Data Processing

Pandas

Database / ETL

SQLAlchemy

Backend API

FastAPI

Machine Learning

Scikit-learn / planned ML components

Version Control

Git

Repository

GitHub

IDE

Visual Studio Code

📁 Project Structure

PII-Detection-Data-Masking/
│
├── api/
│   └── main.py
│
├── catalog/
│   ├── pii_catalog.py
│   └── sensitivity_rules.py
│
├── data/
│   ├── raw_banking.csv
│   ├── raw_education.csv
│   ├── raw_medical.csv
│   ├── raw_marketing.csv
│   ├── dirty_banking.csv
│   ├── dirty_education.csv
│   ├── dirty_medical.csv
│   ├── dirty_marketing.csv
│   └── incoming/
│
├── etl/
│   ├── db.py
│   ├── ingest_bronze.py
│   ├── preprocess_bronze.py
│   ├── validators.py
│   ├── star_banking.py
│   ├── star_education.py
│   ├── star_medical.py
│   └── star_marketing.py
│
├── masking/
│   ├── masking_engine.py
│   └── rbac.py
│
├── ml/
│   ├── data_profiling.py
│   ├── embeddings.py
│   ├── feature_extraction.py
│   ├── pattern_detection.py
│   ├── pii_classifier.py
│   └── train_model.py
│
├── .gitignore
├── README.md
└── requirements.txt

🚀 Getting Started

1. Clone the Repository

git clone https://github.com/Rishav-Kundu/PII-Detection-Data-Masking.git
cd PII-Detection-Data-Masking

2. Create a Virtual Environment

Git Bash

python -m venv .venv
source .venv/Scripts/activate

Windows PowerShell

python -m venv .venv
.venv\Scripts\Activate.ps1

3. Install Dependencies

pip install -r requirements.txt

4. Configure Environment Variables

Create a .env file in the project root.

Example:

DATABASE_URL=your_postgresql_connection_string

Never commit .env or database credentials to GitHub.

5. Prepare an Input CSV

Place a supported CSV inside:

data/incoming/

The ingestion script automatically identifies the domain from the CSV columns.

6. Run Bronze Ingestion

python -m etl.ingest_bronze

7. Run Bronze → Silver

python -m etl.preprocess_bronze

8. Build the Star Schemas

python -m etl.star_banking
python -m etl.star_education
python -m etl.star_medical
python -m etl.star_marketing

🔁 Recommended Development Workflow

1. Place CSV in data/incoming/
             │
             ▼
2. Run Bronze ingestion
             │
             ▼
3. Verify Bronze
             │
             ▼
4. Run Bronze → Silver
             │
             ▼
5. Verify Silver
             │
             ▼
6. Run domain Star ETLs
             │
             ▼
7. Verify Star dimensions/facts
             │
             ▼
8. Run PII profiling / ML layer
             │
             ▼
9. Populate Gold / PII Catalog
             │
             ▼
10. Apply masking + RBAC
             │
             ▼
11. Expose authorized data through API
             │
             ▼
12. Display results in dashboards

🔒 Security Considerations

Because this project deals with potentially sensitive information:

Never commit database credentials.

Never use real PII in development datasets.

Use synthetic or properly anonymized data.

Keep raw/source data separated from user-facing outputs.

Enforce authorization on the backend/API.

Apply least-privilege access.

Mask sensitive fields before exposing them to analyst-level users.

Maintain access and audit information.

Avoid exposing sensitive information through logs or error messages.

Validate ML classification results before using them for enforcement.

Configure PostgreSQL Row Level Security and appropriate authorization policies before exposing the database through a production application.

This is a development/hackathon prototype and should not be treated as a production compliance platform without additional security, testing, monitoring, governance, and operational controls.

📌 Project Status

✅ Completed

Supabase PostgreSQL database setup.

Bronze warehouse layer.

Automatic CSV ingestion.

Automatic domain detection.

Bronze ingestion manifest.

Append-only Bronze processing.

Synthetic clean datasets.

Synthetic dirty test datasets.

Silver warehouse layer.

Incremental Bronze → Silver ETL.

Field-level cleaning and normalization.

Critical-field validation.

Duplicate detection.

Persistent Silver storage.

Banking Star schema.

Education Star schema.

Medical Star schema.

Marketing Star schema.

Incremental Star ETLs.

Star ETL idempotency testing.

Bronze/Silver/Star pipeline validation.

🚧 In Progress / Planned

Complete AI/ML training and evaluation.

Integrate PII classification with the warehouse.

Complete Gold-layer PII analysis.

Complete centralized PII catalog.

Complete dynamic masking workflow.

Complete RBAC implementation.

Complete API integration.

Build dashboard interfaces.

Add PII inventory visualization.

Add sensitivity analysis.

Add masking coverage reporting.

Add access audit reporting.

End-to-end application testing.

Production-oriented security hardening.

🎯 Hackathon Context

This project is developed as a prototype for a PII Detection & Data Masking use case.

The solution combines:

Data Warehousing
       +
ETL & Data Quality
       +
Data Profiling
       +
Pattern Detection
       +
AI/ML Classification
       +
PII Cataloging
       +
Dynamic Masking
       +
RBAC
       +
Governance & Reporting

The completed warehouse foundation ensures that incoming source data can be preserved, cleaned, validated, and organized before PII discovery and protection mechanisms are applied.

👥 Collaboration

Reference datasets are committed under data/ so team members can reproduce tests.

The local ingestion queue is:

data/incoming/

and is ignored by Git.

Do not commit:

.env

Database credentials.

Local virtual environments.

Python cache files.

Temporary ingestion files.

📄 Disclaimer

This project is a hackathon prototype intended for demonstration, development, and educational purposes.

It is not a production-ready compliance, privacy, security, or data-governance system. Production deployment would require additional security testing, access governance, encryption, monitoring, auditing, model validation, data-retention policies, regulatory review, and operational safeguards.

🔗 Repository

https://github.com/Rishav-Kundu/PII-Detection-Data-Masking
