# Operations, observability, and support

## Monitoring

## Logs

## Alerts

## Runbooks

## Incident process

## Support ownership

## Stabilization window

```yaml
stabilization_window:
  duration_days: 14
  exit_criteria:
    zero_open_critical_incidents_for_days: 3
    error_budget_under_threshold: true
    monitoring_confirmed_active: true
    support_handover_complete: true
```
