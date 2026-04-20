# Service Level Objectives

> Maintained by devops agent. Every new endpoint in API_CONTRACTS.md must declare an SLO assignment.

## MVP SLOs (brief §4)
| SLO | Target | Measurement |
|---|---|---|
| Write-path success rate | ≥ 99% rolling 7 days | `bff_write_requests_total{outcome=success}` / total |
| Read-path p95 latency | < 500ms (excludes PuppetDB) | `histogram_quantile(0.95, bff_read_latency_seconds_bucket)` |
| PuppetDB staleness | < 5 min | `bff_puppetdb_staleness_seconds` |

## Burn-rate Alerts
- **Write-path fast-burn:** 2h window exceeds 2× budget consumption → page oncall
- **Write-path slow-burn:** 24h window exceeds 2× budget consumption → ticket
- **Read-path:** sustained p95 > 500ms for 10 min → ticket
- **PuppetDB:** 10% of queries in a 5-min window exceed 5 min staleness → ticket

## Endpoints out of SLO
Document here any endpoint that declares `SLO: none` along with the reason.
