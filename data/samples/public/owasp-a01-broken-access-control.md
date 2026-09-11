# OWASP Top 10:2021 — A01: Broken Access Control

> Source: OWASP Top 10:2021
> URL: https://owasp.org/Top10/2021/A01_2021-Broken_Access_Control/
> License: CC BY 3.0 Unported ("© Copyright 2021-2025 - OWASP Top 10
> Team - This work is licensed under a Creative Commons Attribution 3.0
> Unported License.")
> Retrieved: 2026-09-11
> Quoted passages are direct quotes from the OWASP page; this is a
> condensed excerpt, not the full page. See SOURCES.md for details.

## Overview

Broken Access Control moved to the #1 position in the OWASP Top 10:2021
ranking. According to OWASP, "94% of applications were tested for some
form of broken access control with the average incidence rate of 3.81%,
and has the most occurrences in the contributed dataset with over 318k."

## Description

Access control mechanisms enforce policy such that users cannot act
outside their intended permissions. Failures typically lead to
unauthorized information disclosure, modification, or destruction of
data, or performing a business function outside the user's limits.
Common weaknesses include:

- Least-privilege violations: "access should only be granted for
  particular capabilities, roles, or users, but is available to
  anyone."
- URL parameter tampering and forced-browsing attacks.
- Insecure direct object references allowing unauthorized account
  access.
- Missing access controls on API methods (POST, PUT, DELETE).
- Privilege escalation through authentication bypass or token
  manipulation.
- "CORS misconfiguration allows API access from unauthorized/untrusted
  origins."
- Unauthenticated access to pages or resources that should require
  authentication.
