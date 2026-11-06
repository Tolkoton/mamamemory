# Simplifier — findings for the owner

Nothing listed here was removed.

## 2026-11-05T20:36:21Z — requirements, before M4

### confirm (0)

### flag_only (0)

## 2026-11-05T20:36:33Z — architecture, before M4

### confirm (0)

### flag_only (1)
- APPLIED BY THE ARCHITECT `F-a81ae2e0` **.engine/architecture/architecture-map.md:226-237** — duplication: The M2 convention 'Запис плану: один процес на план' restates the rule already given in M2's plain-words bullet at lines 54-58; the only new content is the base32hex event id and the events.list recognition. The M3 plan.py bullet adds a third copy. The repeated server allowlist rule at lines 238-239 duplicates lines 71-72 and 398-400.
  - applied to the plan 2026-11-05T20:36:49Z: конвенцію «Запис плану» скорочено до посилань і нових деталей (base32hex, events.list); дубль правила входу замінено посиланням — nothing is asked of the owner
  - evidence: read .engine/architecture/architecture-map.md:54 запис плану веде лише один процес; read .engine/architecture/architecture-map.md:226 Запис плану: один процес на план; read .engine/architecture/architecture-map.md:238 Сервер пропускає лише мамин акаунт
  - test safety none, reversal risk low, protected false, traces to: G1

## 2026-11-05T21:25:00Z — f1-skeleton architecture, before slices

### confirm (0)

### flag_only (0)

## 2026-11-05T21:25:05Z — f1-skeleton requirements, before slices

### confirm (0)

### flag_only (0)
