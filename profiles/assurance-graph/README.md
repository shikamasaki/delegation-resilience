# Assurance Graph profile v0alpha1

The Assurance Graph is a derived, deterministic assurance artifact. It connects delegation intent,
attempts, actors, capabilities, external effects, evidence, attestations, claims, dependencies,
exercises, and artifacts so a verifier can explain why a claim is or is not supported.

It is not an execution graph, knowledge graph, GraphRAG index, authorization engine, runtime, or
source of truth. Source artifacts remain authoritative; a graph must be regenerated from them.
`observed` provenance is distinct from `inferred` and `derived` provenance. Inferred relations alone
never promote a claim to `SUPPORTED`. Shared-fate dependencies and invalidation edges weaken claims
to `NOT_DEMONSTRATED` or stale dispositions.

Use `tools/verify_assurance_graph.py` for runner-independent deterministic verification. This profile
does not alter the v0alpha2 transactional-action portable verifier or its packet format.
