# Provider connectivity is intentionally limited to caller-supplied HTTPS
# allowlists. This design creates no NAT gateway, public IP, FTP service, SFTP
# service, route, VPC endpoint, or provider callback listener. A controlled
# egress path and provider contract remain external design prerequisites.

check "provider_connectivity_has_no_default_route" {
  assert {
    condition     = !contains(var.provider_https_cidrs, "0.0.0.0/0")
    error_message = "Provider HTTPS egress must never use an unrestricted IPv4 CIDR."
  }
}
