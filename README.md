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
