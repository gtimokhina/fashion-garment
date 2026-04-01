# Fashion Garment Classification & Inspiration Web App

Lightweight AI-powered web app for fashion designers to organize, search, and reuse inspiration imagery from the field.

## Overview

Design teams collect large numbers of inspiration photos; this project explores turning that library into a searchable, annotated resource with AI-assisted garment classification and designer-added metadata.

## Prerequisites

To be filled in once the application stack is chosen (e.g. Node.js, Python, database requirements).

## Local setup

Setup instructions will be added when the `app/` implementation is in place. The goal is minimal steps to run locally.

## Repository layout

| Path | Purpose |
|------|---------|
| `app/` | Application source (web UI and backend). |
| `eval/` | Model evaluation scripts and labeled test set (50–100 images, gold attributes). |
| `tests/` | Unit tests (e.g. model output parsing), integration tests (filters), end-to-end tests (upload → classify → filter). |
| `tests/unit/` | Unit tests. |
| `tests/integration/` | Integration tests. |
| `tests/e2e/` | End-to-end tests. |

## Architecture

Architectural choices and stack notes will be documented here after implementation.

## Evaluation

See `eval/` for scripts, labeled data, and instructions. A short summary of per-attribute accuracy and model strengths/limitations will be added to this section (or linked from `eval/`).

## Testing

How to run tests will be documented once the test runner and stack are configured. Planned coverage:

- Unit: parsing multimodal model output into structured attributes.
- Integration: filter behavior (especially location and time).
- End-to-end: upload, classify, and filter.
