# User Auth Service — Architecture Overview

Synthetic architecture document for ArchLens development and testing.
No real system, company, or data is represented.

## Purpose

Handles user registration, login, session issuance, and password reset
for the consumer-facing product.

## Components

- **auth-api**: REST API (FastAPI) issuing JWT session tokens.
- **auth-db**: PostgreSQL database storing user records: email address,
  hashed password (bcrypt), full name, date of birth, and account
  status.
- **email-service** (external, third-party SaaS): sends password-reset
  and verification emails. auth-api calls it over HTTPS with an API key
  stored in a secrets manager.
- **session-cache**: Redis cache holding active session tokens with a
  24-hour TTL.

## Data handled

auth-db contains personally identifiable information: email, full name,
date of birth. Password hashes use bcrypt with a per-user salt; raw
passwords are never persisted or logged.

## Known gaps (synthetic, for testing risk/compliance findings)

- Session tokens in session-cache are not currently rotated on
  privilege change (e.g. after a password reset, prior sessions remain
  valid until TTL expiry).
- auth-db has no documented data-retention policy for deactivated
  accounts — records are currently retained indefinitely.
- Audit logging of failed login attempts exists but is not currently
  reviewed on any schedule.

## Ownership

Owned by the Identity team. On-call rotation: identity-oncall.
