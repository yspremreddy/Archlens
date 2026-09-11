# Payment Service Architecture Review

## System Overview

Payment Service is a production web application used to process customer payments.

The architecture contains:

- API Gateway
- Payment Service running on Kubernetes
- PostgreSQL database
- Redis cache
- Object storage for payment receipts

## Network Architecture

Internet traffic enters through the API Gateway.

The API Gateway routes requests to the Payment Service.

The Payment Service connects to PostgreSQL and Redis.

PostgreSQL stores customer and payment information.

The PostgreSQL database is deployed in a public subnet to simplify operational access.

## Security

The database is configured with:

- publicly accessible network access
- username/password authentication
- TLS enabled for application-to-database connections

Customer payment data is encrypted at the application layer before being stored.

## Data Retention

Payment records are retained for 7 years.

Temporary payment-processing data in Redis is retained for 24 hours.

## Compliance Requirements

1. Production customer databases must not be publicly accessible.
2. Customer payment data must be encrypted at rest.
3. Production systems must retain payment records for at least 7 years.
4. External API traffic must use HTTPS.
5. Sensitive production services should run inside private network boundaries.

## Reliability

The Payment Service runs with two Kubernetes replicas.

PostgreSQL currently has a single primary instance and no documented failover configuration.

## Open Questions

- Database backups are not documented.
- Disaster recovery procedures are not documented.
- Database ownership is not assigned to a specific engineering team.
