# Payment Service — Network Architecture

This document describes the (fictional, synthetic) network architecture for
the Payment Service, used for ArchLens development and testing. No real
system, company, or data is represented.

## Components

- **payment-db**: a PostgreSQL database storing production customer
  payment records. PostgreSQL is deployed in a public subnet.

## Compliance requirements

- Production customer databases must not be publicly accessible.

## Ownership

Owned by the Payments Platform team.
