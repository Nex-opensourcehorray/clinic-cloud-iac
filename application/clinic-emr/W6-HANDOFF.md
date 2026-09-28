# Wave 6 Handoff — Lab/Radiology Hybrid Integration

Wave 6 has **not started**. Unlike Waves 4 and 5, it is not covered by their
permanent non-deployment rule. Any Wave 6 implementation must return to the
normal sequence: design, Terraform plan, explicit owner approval, controlled
apply, and live validation.

The next discovery/design mission should address:

- Lab and radiology systems retained on premises.
- Redundant/dual VPN architecture and failure testing.
- Exact allowlisted routes, firewall flows, DNS, and asymmetric-route risk.
- Vendor-supported SFTP or encrypted API/protocols; never plaintext FTP.
- Patient matching and prevention of wrong-patient association.
- Checksums, acknowledgements, bounded retry, replay/idempotency, and duplicate
  handling for results, reports, and images.
- Downtime queueing and a controlled manual fallback with later reconciliation.
- Alerting after five minutes and escalation for unresolved failures after
  fifteen minutes, subject to owner/clinical confirmation.
- Vendor/provider ownership, endpoint, certificate, availability, and support
  dependencies.
- Likely real AWS components, their security boundaries, and cost-sensitive
  resources that require design review and owner approval before planning.

No Wave 6 Terraform, AWS discovery, planning, deployment, or testing is part of
the Wave 5 closeout.
