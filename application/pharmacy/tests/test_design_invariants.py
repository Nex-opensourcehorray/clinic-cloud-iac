from __future__ import annotations

import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = REPOSITORY_ROOT / "modules" / "pharmacy"
VALIDATION_ROOT = REPOSITORY_ROOT / "environments" / "design" / "pharmacy"


class PharmacyDesignInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module_files = {
            path.name: path.read_text(encoding="utf-8")
            for path in MODULE_ROOT.glob("*.tf")
        }
        cls.module = "\n".join(cls.module_files.values())
        cls.security_groups = cls.module_files["security-groups.tf"]
        cls.ec2 = cls.module_files["ec2.tf"]
        cls.rds = cls.module_files["rds.tf"]
        cls.variables = cls.module_files["variables.tf"]
        cls.backup = cls.module_files["backup.tf"]
        cls.connectivity = cls.module_files["provider-connectivity.tf"]
        cls.readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        cls.runbook = (PROJECT_ROOT / "MIGRATION-RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        cls.security_review = (PROJECT_ROOT / "SECURITY-VALIDATION.md").read_text(
            encoding="utf-8"
        )
        cls.validation = "\n".join(
            path.read_text(encoding="utf-8")
            for path in VALIDATION_ROOT.glob("*.tf")
        )

    def test_permanent_non_deployment_status_is_explicit(self) -> None:
        for document in (self.readme, self.security_review):
            self.assertIn("DESIGN VALIDATED — NOT DEPLOYED", document)
            self.assertIn("NEVER DEPLOY", document)

    def test_application_has_no_public_ip_or_rdp(self) -> None:
        self.assertIn("associate_public_ip_address = false", self.ec2)
        self.assertNotIn("3389", self.security_groups)
        self.assertNotRegex(self.security_groups, r'(?m)^\s*cidr_ipv4\s*=\s*"0\.0\.0\.0/0"')

    def test_ec2_requires_imdsv2_and_encrypted_gp3(self) -> None:
        self.assertIn('http_tokens                 = "required"', self.ec2)
        self.assertIn("http_put_response_hop_limit = 1", self.ec2)
        self.assertIn("encrypted             = true", self.ec2)
        self.assertIn('volume_type           = "gp3"', self.ec2)
        self.assertIn("kms_key_id            = var.kms_key_arn", self.ec2)

    def test_database_is_private_single_az_and_encrypted(self) -> None:
        self.assertIn("publicly_accessible    = false", self.rds)
        self.assertIn("multi_az               = false", self.rds)
        self.assertIn("storage_encrypted     = true", self.rds)
        self.assertIn('engine         = "sqlserver-ex"', self.rds)
        self.assertIn("port                = 1433", self.rds)

    def test_sql_ingress_is_application_security_group_only(self) -> None:
        ingress_block = self.security_groups.split(
            'resource "aws_vpc_security_group_ingress_rule" "database_from_application"',
            1,
        )[1].split(
            'resource "aws_vpc_security_group_egress_rule" "application_to_database"',
            1,
        )[0]
        self.assertIn(
            "referenced_security_group_id = aws_security_group.application.id",
            ingress_block,
        )
        self.assertIn("from_port                    = 1433", ingress_block)
        self.assertNotIn("cidr_ipv4", ingress_block)

    def test_provider_egress_requires_exact_nondefault_cidrs(self) -> None:
        self.assertIn("for_each = toset(var.provider_https_cidrs)", self.security_groups)
        self.assertIn('cidr != "0.0.0.0/0"', self.variables)
        self.assertIn(
            '!contains(var.provider_https_cidrs, "0.0.0.0/0")',
            self.connectivity,
        )

    def test_no_iam_or_secret_resource_ownership(self) -> None:
        self.assertNotRegex(self.module, r'resource\s+"aws_iam_')
        self.assertNotRegex(self.module, r'data\s+"aws_iam_')
        self.assertNotRegex(self.module, r'(resource|data)\s+"aws_secretsmanager_')
        self.assertNotIn("secret_string", self.module)

    def test_external_role_secret_and_kms_contracts_are_required(self) -> None:
        for name in (
            "application_role_arn",
            "database_credentials_secret_arn",
            "kms_key_arn",
            "backup_service_role_arn",
        ):
            block = self.variables.split(f'variable "{name}"', 1)[1].split(
                "\n}\n", 1
            )[0]
            self.assertNotIn("default", block)

    def test_database_password_is_ephemeral_and_write_only(self) -> None:
        block = self.variables.split(
            'variable "database_master_password_wo"', 1
        )[1].split("\n}\n", 1)[0]
        self.assertIn("sensitive   = true", block)
        self.assertIn("ephemeral   = true", block)
        self.assertIn("password_wo         = var.database_master_password_wo", self.rds)
        self.assertNotRegex(self.module, r'(?m)^\s*password\s*=')

    def test_database_has_recovery_protections(self) -> None:
        for required in (
            "backup_retention_period",
            "copy_tags_to_snapshot           = true",
            "deletion_protection             = true",
            "skip_final_snapshot             = false",
            "prevent_destroy = true",
        ):
            self.assertIn(required, self.rds)

    def test_backup_design_covers_ec2_and_rds(self) -> None:
        self.assertIn('resource "aws_backup_vault"', self.backup)
        self.assertIn('resource "aws_backup_plan"', self.backup)
        self.assertIn("aws_instance.application.arn", self.backup)
        self.assertIn("aws_db_instance.database.arn", self.backup)
        self.assertIn("delete_after = 35", self.backup)

    def test_no_nat_transfer_dms_or_endpoint_creation(self) -> None:
        for forbidden in (
            'resource "aws_nat_gateway"',
            'resource "aws_transfer_',
            'resource "aws_dms_',
            'resource "aws_vpc_endpoint"',
            'resource "aws_eip"',
        ):
            self.assertNotIn(forbidden, self.module)

    def test_directory_authentication_is_optional_and_guarded(self) -> None:
        self.assertIn('variable "enable_directory_authentication"', self.variables)
        self.assertIn("default     = false", self.variables)
        self.assertIn('check "directory_inputs_are_complete"', self.variables)
        self.assertIn("domain               = var.enable_directory_authentication", self.rds)

    def test_provider_options_cover_auth_retry_and_recovery(self) -> None:
        for option in ("Outbound HTTPS API", "Provider callback", "SFTP"):
            self.assertIn(option, self.readme)
        for control in (
            "Authentication and encryption",
            "idempotency",
            "timeout",
            "reconciliation",
        ):
            self.assertIn(control.lower(), self.readme.lower())
        self.assertIn("FTP is prohibited", self.readme)

    def test_cutover_and_rollback_are_design_only_and_complete(self) -> None:
        for phase in (
            "Pre-cutover",
            "Freeze",
            "Final synchronization",
            "Validate",
            "Go/no-go",
            "Cut over",
            "Rollback",
            "Reconcile",
        ):
            self.assertIn(phase, self.runbook)
        self.assertIn("No live cutover", self.runbook)

    def test_functional_matrix_covers_prescription_and_failure_paths(self) -> None:
        for scenario in (
            "Prescription create",
            "Amendment",
            "Dispense",
            "Duplicate create",
            "Provider timeout/unknown result",
            "Database unavailable",
            "Backup restore",
            "Downtime fallback",
            "Rollback",
            "Post-cutover reconciliation",
        ):
            self.assertIn(scenario, self.runbook)

    def test_security_review_classifies_required_finding_types(self) -> None:
        for classification in (
            "BLOCKER",
            "DESIGN REQUIREMENT",
            "DESIGN CONSTRAINT",
            "COST CONSIDERATION",
            "FOLLOW-UP",
        ):
            self.assertIn(classification, self.security_review)

    def test_validation_root_is_isolated_and_uses_placeholders(self) -> None:
        self.assertNotIn('backend "s3"', self.validation)
        self.assertIn("111122223333", self.validation)
        self.assertNotIn("119033255630", self.validation)
        self.assertIn("skip_credentials_validation = true", self.validation)
        self.assertIn("database_master_password_wo", self.validation)

    def test_design_contains_no_embedded_credentials_or_private_keys(self) -> None:
        combined = "\n".join((self.module, self.validation, self.readme, self.runbook))
        self.assertIsNone(re.search(r"AKIA[A-Z0-9]{16}", combined))
        self.assertNotIn("BEGIN PRIVATE KEY", combined)
        self.assertNotRegex(combined, r'(?m)^\s*aws_secret_access_key\s*=')


if __name__ == "__main__":
    unittest.main()
