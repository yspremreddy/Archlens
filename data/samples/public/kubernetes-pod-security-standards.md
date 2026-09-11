# Kubernetes Pod Security Standards

> Source: Kubernetes documentation, "Pod Security Standards"
> URL: https://kubernetes.io/docs/concepts/security/pod-security-standards/
> License: CC BY 4.0 (Kubernetes documentation license)
> Retrieved: 2026-09-11
> This is a real excerpt of public documentation, condensed for this
> evaluation corpus — not the full page. See SOURCES.md for details.

## Overview

Pod Security Standards define three cumulative policies that range from
highly-permissive to highly-restrictive:

- **Privileged**: unrestricted policy with the widest possible
  permissions. Allows known privilege escalations and is intended for
  system/infrastructure-level workloads managed by privileged, trusted
  users.
- **Baseline**: minimally restrictive policy that prevents known
  privilege escalations while allowing default Pod configurations.
  Targets application operators and developers of non-critical
  applications.
- **Restricted**: heavily restricted policy following current Pod
  hardening best practices. The most stringent of the three.

## Baseline policy controls

The Baseline policy enforces or disallows the following:

- HostProcess: Windows HostProcess containers must be undefined/nil or
  false.
- Host namespaces: `hostNetwork`, `hostPID`, `hostIPC` must be
  undefined/nil or false.
- Privileged containers: `securityContext.privileged` must be
  undefined/nil or false.
- Capabilities: only a small allowed set (AUDIT_WRITE, CHOWN,
  DAC_OVERRIDE, FOWNER, FSETID, KILL, MKNOD, NET_BIND_SERVICE, SETFCAP,
  SETGID, SETPCAP, SETUID, SYS_CHROOT) may be added.
- HostPath volumes: forbidden (must be undefined/nil).
- Host ports: should be undefined/nil or 0.
- Host probes/lifecycle hooks: the host field must be undefined/nil or
  an empty string.
- AppArmor: restricted to RuntimeDefault, Localhost, or undefined.
- SELinux: type limited to container_t, container_init_t,
  container_kvm_t, or container_engine_t; user and role must be
  undefined.
- /proc mount type: must be Default or undefined.
- Seccomp: cannot be Unconfined; limited to RuntimeDefault, Localhost,
  or undefined.
- Sysctls: limited to safe, namespaced sysctls (e.g.
  `kernel.shm_rmid_forced`, `net.ipv4.*` options).

## Key characteristics

Policies are cumulative: Restricted includes all Baseline restrictions,
and both include all aspects not explicitly allowed under Privileged.
Rules apply to containers, initContainers, and ephemeralContainers
alike. Pod-level validation means that if any container in a Pod fails
validation, the entire Pod fails.
