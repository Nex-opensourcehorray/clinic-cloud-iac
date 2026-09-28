# Clinic/EMR RBAC and Clinical UAT Design

Application-layer RBAC is authoritative. Clinical users never receive direct
MySQL credentials. Directory groups may supply identity attributes, but the
application enforces workflow authorization, patient-context scope, separation
of duties, and complete audit events.

## Role design

| Role | Application permissions | Clinical-data scope | Privileged actions | Audit requirements |
|---|---|---|---|---|
| Doctor | Find patient; review history; create/sign/amend encounters; review medications | Assigned/authorized care context plus emergency policy | Sign clinical record, controlled amendment | Read context, create/update/sign, before/after metadata, reason |
| Nurse | Patient workflow, observations, tasks, medication workflow as vendor permits | Assigned ward/team/patient context | Record observations and execute authorized tasks; no physician signature | Patient context, task transition, actor/time, exception |
| Reception | Registration, demographics, appointments | Minimum demographic/scheduling fields; no clinical notes by default | Merge/correct identity only through governed workflow | Searches, demographic changes, merges, appointment mutations |
| Clinic Manager | Operational queues and approved aggregate reporting | Operational minimum; clinical detail only when explicitly justified | Workflow configuration or approval separated from IT administration | Reports, exports, configuration/approval changes |
| IT Administrator | Service health, configuration deployment, backup/restore orchestration | No routine clinical-record access | Platform operations through approved elevation; no clinical workflow edits | Elevation, commands, configuration, recovery action, outcome |
| Security Administrator | Audit search, alert investigation, access review | Minimum event metadata; clinical payload revealed only through approved case | Disable access, preserve evidence, review break-glass | Query, case, scope, export, decision, evidence custody |
| Break Glass | Temporary emergency access beyond normal context | Only the patient/record and duration justified by emergency | Explicit activation; no standing elevated role | Strong authentication, reason, patient/context, actions, alert, post-use review |

## Break-glass controls

1. Named identity with strong authentication and no shared credentials.
2. Explicit activation and reason; time-limited authorization scoped to the
   minimum clinical context.
3. Immediate high-priority security/clinical notification.
4. Immutable record of initiation, searches, reads, exports, changes, and end.
5. Mandatory post-use review by security and clinical ownership, including any
   inappropriate access response.
6. Periodic synthetic exercise; routine use is a control failure.

## Role-based UAT matrix

No live UAT was executed. Future cases use synthetic records only.

| Role | Synthetic UAT scenarios | Required result |
|---|---|---|
| Doctor | Find patient, review history, create/update/sign encounter, review medication | Complete clinical history; permitted mutations only; immutable audit chain |
| Nurse | Locate assigned patient, record observation/task, attempt physician-only action | Normal tasks succeed; physician-only action denied and audited |
| Reception | Register patient, schedule/reschedule appointment, attempt clinical-note access | Minimum workflow succeeds; clinical content denied |
| Clinic Manager | Review queue/aggregate report, attempt unauthorized clinical export | Approved operational view succeeds; excessive detail/export denied |
| IT | Inspect health, restart through controlled workflow, attempt application record search | Operational action audited; clinical search denied |
| Security | Search synthetic audit event, investigate denied access, preserve evidence | Complete searchable trail without unnecessary clinical payload |
| Break Glass | Activate with reason, access one synthetic patient, end session | Alert, bounded access, complete event trail, mandatory review |

Cross-role negative tests verify horizontal/vertical authorization, stale group
membership, disabled users, session expiry, concurrent access, export limits,
and denial behavior during directory or audit-service degradation.
