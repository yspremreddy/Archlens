# Analytics Data Pipeline — Architecture Overview

Synthetic architecture document for ArchLens development and testing.
No real system, company, or data is represented.

## Purpose

Ingests event data from the product's client applications and loads it
into the analytics warehouse for internal reporting.

## Components

- **event-collector**: public ingestion endpoint receiving client
  events over HTTPS.
- **event-bus**: Kafka topic buffering raw events.
- **etl-worker**: batch job (runs hourly) that transforms and loads
  events from event-bus into analytics-warehouse.
- **analytics-warehouse**: columnar data warehouse holding transformed
  event data, retained for 2 years for trend analysis.

## Data handled

Raw events may include user id, device identifiers, approximate
location (derived from IP, truncated to city-level), and in-app action
names. Analytics-warehouse retains this data in aggregate and
per-user-id form for 2 years.

## Known gaps (synthetic, for testing risk/compliance findings)

- There is no documented mechanism for honoring a user deletion request
  against analytics-warehouse — deletion is currently a manual,
  case-by-case SQL operation.
- event-collector accepts events from any authenticated client without
  schema validation, so malformed or unexpected fields can reach
  event-bus and etl-worker unfiltered.
- No component in this pipeline has an assigned data-protection owner
  distinct from the on-call engineer.

## Ownership

Owned by the Data Platform team. On-call rotation: data-platform-oncall.
