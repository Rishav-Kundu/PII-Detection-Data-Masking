# PII Detection & Data Masking

A compliance-oriented data warehouse prototype for discovering, classifying, cataloging, and masking Personally Identifiable Information (PII) using rule-based pattern detection and AI/ML-assisted classification.

## 📌 Overview

Organizations store sensitive information across multiple systems such as banking, education, healthcare, and marketing databases. Manually identifying sensitive data and applying consistent masking policies can be difficult and error-prone.

This project provides an automated pipeline for:

- Ingesting source data into a **Bronze Layer**
- Cleaning and validating data into a **Silver Layer**
- Profiling datasets and detecting PII-related patterns
- Using AI/ML-assisted techniques to classify sensitive data
- Maintaining a centralized **PII Catalog**
- Applying **role-based dynamic masking**
- Providing APIs and dashboards for monitoring and reporting

## 🏗️ Architecture

```text
                    ┌─────────────────────┐
                    │     Data Sources    │
                    │                     │
                    │ CRM / HR / Finance  │
                    │ Banking / Education │
                    │ Medical / Marketing │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Bronze Layer     │
                    │   Raw Source Data   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   ETL / Profiling   │
                    │                     │
                    │ Cleaning            │
                    │ Validation          │
                    │ Type Conversion     │
                    │ Pattern Detection   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │     Silver Layer    │
                    │ Clean & Validated   │
                    │       Data          │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    AI/ML Pipeline   │
                    │                     │
                    │ Feature Extraction  │
                    │ Embeddings          │
                    │ PII Classification  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │     PII Catalog     │
                    │                     │
                    │ PII Type            │
                    │ Sensitivity         │
                    │ Confidence          │
                    │ Detection Method    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Masking + RBAC     │
                    │                     │
                    │ Admin → Full Data   │
                    │ Analyst → Masked    │
                    │ Unauthorized → Deny │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Dashboard & Reports │
                    └─────────────────────┘

🎯 Objectives

The primary objectives of the project are:

Automatically discover potentially sensitive information.
Classify columns based on PII characteristics.
Maintain a centralized inventory of sensitive data.
Apply masking policies based on user roles.
Provide visibility into PII distribution and masking coverage.
Support data governance, compliance, and auditing.
📊 Data Domains

The prototype currently works with four synthetic datasets:

🏦 Banking

Contains information such as:

Customer ID
First Name
Last Name
Email
Phone
Date of Birth
Account Number
Account Type
Balance
Address
🎓 Education

Contains:

Student ID
First Name
Last Name
Email
Phone
Date of Birth
Address
Course
Department
Enrollment Date
Percentage
🏥 Medical

Contains:

Patient ID
First Name
Last Name
Email
Phone
Date of Birth
Address
Blood Group
Diagnosis
Doctor Name
Admission Date
Medical Record Number
📢 Marketing

Contains:

Customer ID
First Name
Last Name
Email
Phone
Address
Age
Gender
Campaign Name
Campaign Date
Channel

Note: All datasets used for development and testing are synthetic and do not contain real customer, patient, student, or financial information.

🗄️ Data Warehouse

The project follows a layered data warehouse architecture.

Bronze Layer

The Bronze layer stores incoming source data in its raw representation.

Source fields are initially stored as text to preserve the original incoming values before transformation and validation.

Bronze Tables
bronze.banking
bronze.education
bronze.medical
bronze.marketing
Silver Layer

The Silver layer contains cleaned, standardized, typed, and validated data.

The ETL process performs:

Whitespace removal
Email normalization
Phone-number normalization
Categorical value standardization
Date conversion
Numeric conversion
Required-field validation
Uniqueness validation
Domain validation
Constraint validation
Silver Tables
silver.banking
silver.education
silver.medical
silver.marketing
🔄 Bronze → Silver ETL

The ETL pipeline follows these steps:

                    Bronze Data
                         │
                         ▼
                  Read Source Tables
                         │
                         ▼
                 Clean & Normalize
                         │
                         ▼
                  Convert Data Types
                         │
                         ▼
                    Validate Data
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
        Valid Records           Invalid Records
              │                     │
              ▼                     ▼
        Silver Tables            Rejected

The ETL pipeline performs:

Connect to PostgreSQL/Supabase.
Read records from the Bronze tables.
Trim and standardize source values.
Normalize formats such as email and categorical values.
Convert text values into appropriate database types.
Validate required fields and domain rules.
Reject invalid records rather than fabricating missing information.
Insert validated records into the Silver tables.
Current Sample Data
Banking     → 25 records
Education   → 25 records
Medical     → 25 records
Marketing   → 25 records
--------------------------------
Total       → 100 records

The current sample environment successfully processes the sample records from Bronze into Silver.

🤖 AI/ML-Based PII Discovery

The project combines deterministic pattern detection with machine-learning-assisted classification.

1. Pattern Detection

The system profiles columns and analyzes their observed characteristics.

Examples include patterns for:

Email addresses
Indian phone numbers
Dates
Account numbers
Medical record numbers
Other identifiable fields

Pattern matching produces numerical features such as pattern-match ratios.

2. Data Profiling

The profiling stage analyzes characteristics such as:

Data type
Null percentage
Uniqueness
Average value length
Pattern-match percentage
Column context
Table context

These features provide useful signals for identifying potentially sensitive columns.

3. Semantic Embeddings

Column context can be converted into semantic embeddings.

The semantic context can include:

Table Name
Column Name
Data Type
Privacy-safe description
Observed characteristics

For example:

Table: customers
Column: customer_email
Data Type: VARCHAR
Email pattern match: 98.7%
Unique values: 97%
Average length: 21
Null percentage: 1%

Semantic embeddings help identify columns that are conceptually similar even when their names differ.

4. PII Classification

The prototype supports machine-learning models such as:

Logistic Regression
XGBoost

The classifier can generate:

Predicted PII Category
Confidence Score
Detection Information

The classification results can then be used by the PII catalog and masking engine.

📚 PII Catalog

The PII Catalog provides a centralized inventory of detected sensitive information.

Typical catalog information includes:

Metadata	Description
Domain	Source/business domain
Table	Source table
Column	Sensitive column
PII Type	Category of detected PII
Sensitivity	Sensitivity classification
Detection Method	Pattern / ML / Combined
Confidence	Classification confidence
Masking Status	Whether masking is applied
Example
Domain: Banking
Table: banking
Column: email
PII Type: Email
Sensitivity: High
Detection Method: Pattern + ML
Confidence: 0.97
Masking: Enabled
🔐 Dynamic Data Masking

The masking engine protects sensitive information according to the user's role.

Access Model
                    ┌───────────────┐
                    │     User      │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │     RBAC      │
                    └───────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
           Admin         Analyst      Unauthorized
              │             │             │
              ▼             ▼             ▼
          Full Data     Masked Data      Denied
Masking Examples
Email
Original:  aarav.sharma@example.com
Masked:    a****@example.com
Phone
Original:  9876543210
Masked:    ******3210
Account Number
Original:  123456789012
Masked:    ********9012

The exact masking behavior is controlled by the project's masking policies.

👥 Role-Based Access Control

The system is designed around role-based access.

Role	Access
Administrator	Full/authorized sensitive data
Analyst	Masked sensitive data
Unauthorized User	Restricted access

This approach helps enforce least-privilege access to sensitive information.

📈 Dashboard & Reporting

The planned dashboard provides visibility into the PII discovery and masking process.

PII Inventory

Shows:

Total detected PII
PII by domain
PII by table
PII by column
PII categories
Sensitivity Heatmap

Visualizes the distribution of sensitive information across datasets.

Masking Coverage

Shows:

Total Sensitive Fields
          vs.
Masked Sensitive Fields
Access Audit

Tracks access activity related to sensitive data.

Potential audit information includes:

User/role
Accessed resource
Timestamp
Action
Access result
🛠️ Technology Stack
Component	Technology
Programming Language	Python
Database	PostgreSQL
Data Warehouse	Supabase PostgreSQL
Data Processing	Pandas
Machine Learning	Scikit-learn
ML Model	XGBoost
Embeddings	Sentence Transformers
Backend API	FastAPI
Version Control	Git
Repository	GitHub
IDE	Visual Studio Code
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
├── etl/
│   ├── db.py
│   ├── preprocess_bronze.py
│   └── validators.py
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
python -m venv .venv
Git Bash
source .venv/Scripts/activate
Windows PowerShell
.venv\Scripts\Activate.ps1
3. Install Dependencies
pip install -r requirements.txt
4. Configure Environment Variables

Create a .env file in the project root.

Example:

DB_HOST=your_database_host
DB_PORT=5432
DB_NAME=postgres
DB_USER=your_database_user
DB_PASSWORD=your_database_password

Never commit .env or database credentials to GitHub.

5. Run Bronze → Silver ETL
python etl/preprocess_bronze.py
6. Run the FastAPI Backend
uvicorn api.main:app --reload

The API and dashboard components are being developed and integrated as the project progresses.

🔒 Security Considerations

Because this project deals with PII detection and masking, security is an important part of the design.

Never commit database credentials.
Never use real PII in development datasets.
Use synthetic or properly anonymized data.
Apply role-based access control.
Follow least-privilege principles.
Maintain access and audit information.
Validate ML classification results before applying production enforcement.
Do not expose sensitive information through logs or error messages.
📌 Project Status
Completed
 Supabase PostgreSQL database setup
 Bronze data warehouse layer
 Silver data warehouse layer
 Synthetic sample datasets
 Bronze → Silver ETL pipeline
 Data validation
 Data profiling foundation
 PII pattern detection foundation
 ML feature extraction foundation
 Embedding pipeline foundation
 PII classifier foundation
 PII catalog foundation
 Masking engine foundation
 RBAC foundation
 FastAPI backend foundation
In Progress
 Complete AI/ML training and evaluation
 Integrate PII classifier with catalog
 Complete dynamic masking workflow
 Complete API integration
 Build dashboard
 Add PII inventory visualizations
 Add sensitivity heatmap
 Add masking coverage reporting
 Add access audit reporting
 End-to-end integration testing
🎯 Hackathon Context

This project is developed as a prototype for the PII Detection & Data Masking use case.

The solution combines:

Data Warehousing
       +
Data Profiling
       +
Pattern Detection
       +
AI/ML Classification
       +
PII Cataloging
       +
Role-Based Masking
       +
Governance & Reporting

The overall goal is to provide a compliance-oriented approach for discovering sensitive information and controlling how that information is accessed and displayed.

🔗 Repository

GitHub Repository:

https://github.com/Rishav-Kundu/PII-Detection-Data-Masking

Disclaimer: This project is a hackathon prototype intended for demonstration, development, and educational purposes. It should not be considered a production-ready compliance system without additional security, validation, monitoring, and governance controls.
