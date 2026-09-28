from __future__ import annotations

import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = REPOSITORY_ROOT / "modules" / "clinic-emr"
VALIDATION_ROOT = REPOSITORY_ROOT / "environments" / "design" / "clinic-emr"


class ClinicEmrDesignInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module_files = {
            path.name: path.read_text(encoding="utf-8")
            for path in MODULE_ROOT.glob("*.tf")
        }
        cls.module = "\n".join(cls.module_files.values())
        cls.security_groups = cls.module_files["security-groups.tf"]
        cls.compute = cls.module_files["compute.tf"]
        cls.rds = cls.module_files["rds.tf"]
        cls.dms = cls.module_files["dms.tf"]
        cls.variables = cls.module_files["variables.tf"]
        cls.backup = cls.module_files["backup.tf"]
        cls.readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        cls.runbook = (PROJECT_ROOT / "MIGRATION-RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        cls.rbac_uat = (PROJECT_ROOT / "RBAC-UAT.md").read_text(encoding="utf-8")
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

    def test_application_is_private(self) -> None:
        self.assertIn("associate_public_ip_address = false", self.compute)
        self.assertNotRegex(self.security_groups, r"(?m)^\s*from_port\s*=\s*(22|3389)$")
        self.assertNotRegex(self.security_groups, r"(?m)^\s*to_port\s*=\s*(22|3389)$")

    def test_application_requires_imdsv2_and_encrypted_gp3(self) -> None:
        self.assertIn('http_tokens                 = "required"', self.compute)
        self.assertIn("http_put_response_hop_limit = 1", self.compute)
        self.assertIn("encrypted             = true", self.compute)
        self.assertIn('volume_type           = "gp3"', self.compute)
        self.assertIn("kms_key_id            = var.kms_key_arn", self.compute)

    def test_database_is_private_mysql_single_az_and_encrypted(self) -> None:
        for required in (
            'engine         = "mysql"',
            "publicly_accessible    = false",
            "multi_az               = false",
            "storage_encrypted     = true",
            "port                = 3306",
        ):
            self.assertIn(required, self.rds)

    def test_database_requires_tls(self) -> None:
        self.assertIn('name  = "require_secure_transport"', self.rds)
        self.assertIn('value = "1"', self.rds)

    def test_database_has_recovery_protections(self) -> None:
        for required in (
            "backup_retention_period",
            "copy_tags_to_snapshot           = true",
            "deletion_protection             = true",
            "skip_final_snapshot             = false",
            "prevent_destroy = true",
        ):
            self.assertIn(required, self.rds)

    def test_database_ingress_uses_application_and_dms_sgs_only(self) -> None:
        application_block = self.security_groups.split(
            'resource "aws_vpc_security_group_ingress_rule" "database_from_application"',
            1,
        )[1].split(
            'resource "aws_vpc_security_group_ingress_rule" "database_from_dms"',
            1,
        )[0]
        dms_block = self.security_groups.split(
            'resource "aws_vpc_security_group_ingress_rule" "database_from_dms"',
            1,
        )[1].split(
            'resource "aws_vpc_security_group_egress_rule" "application_to_database"',
            1,
        )[0]
        self.assertIn("aws_security_group.application.id", application_block)
        self.assertIn("aws_security_group.dms.id", dms_block)
        for block in (application_block, dms_block):
            self.assertIn("from_port                    = 3306", block)
            self.assertNotIn("cidr_ipv4", block)

    def test_dms_is_private_full_load_and_cdc(self) -> None:
        self.assertIn("publicly_accessible         = false", self.dms)
        self.assertIn('migration_type           = "full-load-and-cdc"', self.dms)
        self.assertIn("replication_subnet_group_id", self.dms)
        self.assertIn("aws_security_group.dms.id", self.dms)

    def test_dms_endpoints_use_external_secrets_and_verified_tls(self) -> None:
        self.assertEqual(self.dms.count('ssl_mode                        = "verify-full"'), 2)
        self.assertIn("secrets_manager_arn             = var.dms_source_secret_arn", self.dms)
        self.assertIn("secrets_manager_arn             = var.dms_target_secret_arn", self.dms)
        self.assertEqual(
            self.dms.count(
                "secrets_manager_access_role_arn = var.dms_secrets_access_role_arn"
            ),
            2,
        )

    def test_dms_task_enables_validation_and_bounded_logging(self) -> None:
        self.assertIn("EnableLogging = true", self.dms)
        self.assertIn("EnableValidation = true", self.dms)
        self.assertIn("LOGGER_SEVERITY_DEFAULT", self.dms)
        self.assertNotIn("LOGGER_SEVERITY_DETAILED_DEBUG", self.dms)

    def test_dms_lob_and_error_handling_fail_safely(self) -> None:
        for required in (
            "LimitedSizeLobMode = true",
            "LobMaxSize         = 32",
            'DataErrorPolicy               = "STOP_TASK"',
            'DataTruncationErrorPolicy     = "STOP_TASK"',
            'TableErrorPolicy              = "STOP_TASK"',
            "StopTaskCachedChangesApplied    = false",
            "StopTaskCachedChangesNotApplied = false",
        ):
            self.assertIn(required, self.dms)

    def test_dms_table_mapping_is_schema_scoped(self) -> None:
        self.assertIn('"schema-name" = var.source_schema_name', self.dms)
        self.assertIn('"table-name"  = "%"', self.dms)
        self.assertNotIn('"schema-name" = "%"', self.dms)

    def test_source_and_target_flows_are_narrow(self) -> None:
        self.assertIn("for_each = toset(var.source_database_cidrs)", self.security_groups)
        self.assertIn("referenced_security_group_id = aws_security_group.database.id", self.security_groups)
        self.assertIn("from_port         = 3306", self.security_groups)
        self.assertIn("from_port                    = 3306", self.security_groups)

    def test_no_unrestricted_cidr(self) -> None:
        self.assertNotRegex(self.security_groups, r'cidr_ipv4\s*=\s*"0\.0\.0\.0/0"')
        self.assertIn('cidr != "0.0.0.0/0"', self.variables)
        self.assertIn("no_default_route_allowlists", self.variables)

    def test_dns_is_exactly_scoped_for_application_and_dms(self) -> None:
        self.assertEqual(
            self.security_groups.count("cidr_ipv4         = var.dns_resolver_cidr"),
            4,
        )
        self.assertIn("application_dns_udp", self.security_groups)
        self.assertIn("dms_dns_tcp", self.security_groups)

    def test_no_iam_or_secret_resource_ownership(self) -> None:
        self.assertNotRegex(self.module, r'resource\s+"aws_iam_')
        self.assertNotRegex(self.module, r'data\s+"aws_iam_')
        self.assertNotRegex(self.module, r'(resource|data)\s+"aws_secretsmanager_')
        self.assertNotIn("secret_string", self.module)

    def test_external_identity_secret_kms_contracts_are_required(self) -> None:
        for name in (
            "application_role_arn",
            "database_credentials_secret_arn",
            "dms_source_secret_arn",
            "dms_target_secret_arn",
            "dms_secrets_access_role_arn",
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
        self.assertNotRegex(self.module, r"(?m)^\s*password\s*=")

    def test_no_nat_endpoint_vpn_or_route_creation(self) -> None:
        for forbidden in (
            'resource "aws_nat_gateway"',
            'resource "aws_vpc_endpoint"',
            'resource "aws_vpn_',
            'resource "aws_route"',
            'resource "aws_eip"',
        ):
            self.assertNotIn(forbidden, self.module)

    def test_fsx_is_external_and_optional(self) -> None:
        self.assertNotIn('resource "aws_fsx_', self.module)
        self.assertIn("existing_fsx_security_group_id", self.variables)
        self.assertIn("existing_fsx_arn", self.variables)
        self.assertIn("application_to_fsx", self.security_groups)

    def test_backup_design_covers_compute_database_and_optional_fsx(self) -> None:
        self.assertIn('resource "aws_backup_vault"', self.backup)
        self.assertIn('resource "aws_backup_plan"', self.backup)
        self.assertIn("aws_instance.application.arn", self.backup)
        self.assertIn("aws_db_instance.database.arn", self.backup)
        self.assertIn("var.existing_fsx_arn", self.backup)
        self.assertIn("delete_after = 35", self.backup)

    def test_documentation_separates_known_and_unknown(self) -> None:
        for phrase in (
            "Known portfolio facts",
            "Unknown and requiring source/vendor/owner confirmation",
            "No compatibility, performance, migration, UAT, restore, or clinical outcome",
        ):
            self.assertIn(phrase, self.readme)

    def test_data_classification_covers_required_categories(self) -> None:
        for value in (
            "Patient demographics",
            "Appointments",
            "Encounters",
            "medication history",
            "Billing references",
            "User/account metadata",
            "Audit history",
            "Attachments and file references",
            "PHI",
            "PII",
            "Operational/security metadata",
        ):
            self.assertIn(value.lower(), self.readme.lower())

    def test_rbac_covers_all_required_roles(self) -> None:
        for role in (
            "Doctor",
            "Nurse",
            "Reception",
            "Clinic Manager",
            "IT Administrator",
            "Security Administrator",
            "Break Glass",
        ):
            self.assertIn(role, self.rbac_uat)

    def test_rbac_prohibits_direct_clinical_database_access(self) -> None:
        self.assertIn("never receive direct", self.rbac_uat)
        self.assertIn("MySQL credentials", self.rbac_uat)
        for control in (
            "Explicit activation",
            "strong authentication",
            "reason",
            "post-use review",
        ):
            self.assertIn(control.lower(), self.rbac_uat.lower())

    def test_integrity_plan_covers_required_controls(self) -> None:
        for control in (
            "Row counts",
            "Primary identifiers",
            "Referential integrity",
            "Null/value distributions",
            "Timestamps",
            "Encoding/collation",
            "Duplicate detection",
            "Deleted records",
            "Clinical history",
            "Audit continuity",
        ):
            self.assertIn(control, self.runbook)

    def test_cdc_matrix_covers_failure_paths(self) -> None:
        for scenario in (
            "Insert propagation",
            "Update propagation",
            "Delete propagation",
            "High-change interval",
            "Replication lag",
            "DMS restart",
            "Network interruption",
            "Duplicate prevention",
            "Source/target reconciliation",
            "OWNER / CLINICAL DECISION REQUIRED",
        ):
            self.assertIn(scenario, self.runbook)

    def test_clinical_uat_is_role_based_and_not_claimed_live(self) -> None:
        self.assertIn("No live UAT was executed", self.rbac_uat)
        for scenario in (
            "find patient",
            "review history",
            "create/update/sign encounter",
            "patient",
            "appointment",
            "audit",
            "Break Glass",
        ):
            self.assertIn(scenario.lower(), self.rbac_uat.lower())

    def test_cutover_design_has_all_required_steps(self) -> None:
        for phase in (
            "Readiness checks",
            "Freeze/change-control",
            "Full-load completion",
            "Monitor CDC",
            "Final source-write freeze",
            "Catch up",
            "Integrity validation",
            "Connection switch",
            "Role smoke/UAT",
            "Go/no-go",
            "Reconcile",
        ):
            self.assertIn(phase, self.runbook)
        self.assertIn("No step above was executed", self.runbook)

    def test_rollback_design_preserves_and_reconciles_transactions(self) -> None:
        for phrase in (
            "Stop target writes",
            "target-only transaction",
            "Return applications to the source",
            "Reconcile captured downtime",
            "forward-fix",
            "was not rehearsed live",
        ):
            self.assertIn(phrase.lower(), self.runbook.lower())

    def test_security_review_classifies_required_findings(self) -> None:
        for classification in (
            "BLOCKER",
            "DESIGN REQUIREMENT",
            "DESIGN CONSTRAINT",
            "FOLLOW-UP",
        ):
            self.assertIn(classification, self.security_review)

    def test_security_review_covers_required_threats(self) -> None:
        for threat in (
            "Public database exposure",
            "Credential compromise",
            "Excessive privileges",
            "Ransomware",
            "DMS endpoint secret exposure",
            "Migration-log PHI leakage",
            "CDC integrity failure",
            "Unauthorized schema changes",
            "Audit-loss risk",
            "Insecure rollback",
            "Break-glass misuse",
            "Shared-file/database inconsistency",
        ):
            self.assertIn(threat, self.security_review)

    def test_validation_root_is_isolated_and_placeholder_only(self) -> None:
        self.assertNotIn('backend "s3"', self.validation)
        self.assertIn("111122223333", self.validation)
        self.assertNotIn("119033255630", self.validation)
        self.assertIn("skip_credentials_validation = true", self.validation)
        self.assertIn("database_master_password_wo", self.validation)

    def test_design_contains_no_embedded_credentials_or_private_keys(self) -> None:
        combined = "\n".join(
            (
                self.module,
                self.validation,
                self.readme,
                self.runbook,
                self.rbac_uat,
            )
        )
        self.assertIsNone(re.search(r"AKIA[A-Z0-9]{16}", combined))
        self.assertNotIn("-----BEGIN PRIVATE KEY-----", combined)
        self.assertNotRegex(combined, r"(?m)^\s*aws_secret_access_key\s*=")


if __name__ == "__main__":
    unittest.main()
