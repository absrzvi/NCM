# Data Model

> Maintained by architect and bff-dev agents.
> Contains all Pydantic v2 models used in the BFF.
> Single-tenant MVP — NO `customer_id` on any model.

---

## Model Template

```python
from pydantic import BaseModel
from typing import Optional

class ExampleModel(BaseModel):
    id: str
    # NO customer_id — single-tenant MVP (D3)
    # ... fields
```

## Canonical Models (expected, from brief §12)
User, Role, Environment, Fleet, Train, Device, HieradataTree, HieradataNode, Parameter, ParameterValue, DraftChangeSet, DraftParameterEdit, DriftRecord, PuppetReport, ChangeSubmission, MergeRequestSummary, DeploymentStatus, ForceRunRequest, ForceRunResult, EnvelopeRejection, BenchAllowlist, EnvironmentConfig, LayerDescriptor, ProbeReport, OnboardingDraft, FileInventoryEntry, ValidationGateResult, AuditEvent, Job, ParameterHistoryEntry (D16), IdempotencyKey (D4), HealthCheckResult (§8), SLOStatus (§4).
