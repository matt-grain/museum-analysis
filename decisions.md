# Architecture Decision Records

## 2026-04-16 — Add allow_indirect_imports to routers import-linter contract

**Status:** accepted

**Context:**
Phase 5 introduced `dependencies.py` as the central DI wiring layer. This file necessarily imports repositories, models, and clients (it is their factory). The `museums.routers` import-linter contract was configured without `allow_indirect_imports`, causing all transitive paths through `dependencies.py` to fail the "Routers cannot import repositories, models, or clients" contract.

**Decision:**
Add `allow_indirect_imports = "True"` to the routers contract. Direct imports from any router file into repositories/models/clients remain forbidden — the contract still catches the architectural violation it was designed for. Transitive paths through `dependencies.py` are permitted because `dependencies.py` is explicitly the wiring layer whose job is to import and compose these modules.

**Alternatives considered:**
- Remove `dependencies.py` and inject raw `Session` / clients into routers directly — violates layered architecture.
- Exclude `dependencies.py` from the router contract — more complex configuration, achieves the same result.
- Use `allow_indirect_imports` — simplest, consistent with how the services/sqlalchemy contract is already handled in this project.

**Consequences:**
A router could import `dependencies.py` which imports repositories without triggering the contract. However, this is the intended usage pattern (routers must import deps to get their `Annotated` aliases). Direct repository imports from routers are still caught.
