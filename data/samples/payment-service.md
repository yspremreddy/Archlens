# Payment Service — Architecture Overview

This document describes the (fictional, synthetic) Payment Service used
for ArchLens development and testing. No real system, company, or data
is represented.

## Purpose

The Payment Service processes customer checkout transactions, stores
payment method tokens, and emits settlement events to the ledger system.

## Components

- **payment-api**: public-facing REST API (FastAPI) that accepts
  checkout requests. Deployed in `us-east-1`.
- **payment-db**: PostgreSQL database storing transaction records and
  tokenized card references. Not the card numbers themselves — those are
  handled by a third-party PCI-compliant vault. Deployed in `us-east-1`.
- **settlement-queue**: a message queue (Kafka) carrying settlement
  events from payment-api to the ledger-service.
- **ledger-service**: downstream service (owned by the Finance
  Engineering team) that reconciles settlement events into the general
  ledger.

## Data handled

payment-db stores: transaction amount, currency, customer id, card
token (not raw PAN), billing postal code, and timestamp. Billing postal
code is retained for fraud-scoring purposes for 90 days, then purged by
a nightly job.

## Known gaps (synthetic, for testing risk/compliance findings)

- payment-api currently has no documented rate limiting on the checkout
  endpoint.
- The 90-day postal-code purge job has no automated test verifying it
  actually runs (manual verification only, last checked over a year
  ago).
- settlement-queue messages are not currently encrypted at rest by
  application-level controls beyond the underlying broker's disk
  encryption.

## Ownership

Owned by the Payments Platform team. On-call rotation: payments-oncall.
