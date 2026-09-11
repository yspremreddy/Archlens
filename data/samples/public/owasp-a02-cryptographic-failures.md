# OWASP Top 10:2021 — A02: Cryptographic Failures

> Source: OWASP Top 10:2021
> URL: https://owasp.org/Top10/2021/A02_2021-Cryptographic_Failures/
> License: CC BY 3.0 Unported ("© Copyright 2021-2025 - OWASP Top 10
> Team - This work is licensed under a Creative Commons Attribution 3.0
> Unported License.")
> Retrieved: 2026-09-11
> Quoted passages are direct quotes from the OWASP page; this is a
> condensed excerpt, not the full page. See SOURCES.md for details.

## Overview

Cryptographic Failures moved to the #2 position in the OWASP Top
10:2021 ranking, previously titled "Sensitive Data Exposure." As OWASP
states, "the focus is on failures related to cryptography (or lack
thereof), which often lead to exposure of sensitive data."

## Common failure categories

- Hard-coded passwords and cryptographic keys.
- Broken or risky cryptographic algorithms in use.
- Insufficient entropy in random number generation.
- "Is any data transmitted in clear text?" — across protocols like
  HTTP, SMTP, and FTP.
- Deprecated algorithms and weak cryptographic protocols still in use.
- Default or weak cryptographic keys without proper rotation.
- Missing enforcement of encryption and security headers.
- Improper certificate validation.
- Unsafe initialization-vector handling, or use of insecure modes like
  ECB.
- Passwords used directly as cryptographic keys without proper key
  derivation.
- Deprecated hash functions (MD5, SHA1) and padding methods.
- Cryptographic error messages or side channels that leak information
  exploitable by an attacker.
