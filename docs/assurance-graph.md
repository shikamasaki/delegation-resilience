# Assurance Graph: semantics and boundary

## What this graph is

An Assurance Graph is a deterministic, derived relationship model for delegated work. Its nodes
and edges bind intent, attempts, actors, capabilities, external effects, evidence, attestations,
claims, dependencies, exercises, and artifacts to source artifact IDs, digests, and observation
times. It answers: “which observed artifacts and relationships are being used to support this
claim, and what can invalidate that support?”

It is deliberately a profile separate from the Universal Core. The profile owns graph vocabulary
and graph-specific verification; adapters such as OrgForge only translate their evidence into this
format and cannot redefine what `supports`, `shares_fate_with`, or `invalidates` mean.

The v0alpha1 endpoint semantics are intentionally closed:

| Edge | From | To |
| --- | --- | --- |
| `attempts` | intent | attempt |
| `uses` | attempt | capability, actor, dependency |
| `produces` | attempt | external effect, evidence, artifact |
| `observes` | attestation, exercise, evidence | evidence, external effect, attempt |
| `reconciles` | attempt, evidence, attestation, exercise | external effect |
| `supports` | evidence, attestation, exercise, artifact | claim |
| `depends_on` | claim, attempt, exercise | dependency |
| `invalidates` | dependency, evidence, attestation, artifact | claim, attestation |
| `shares_fate_with` | dependency | dependency |
| `hands_off_to` | attempt, actor, capability | actor, capability, attempt |
| `produces_artifact` | exercise, attempt, attestation | artifact |

Unknown endpoint combinations are rejected; adapters cannot use an existing edge name with a new
meaning.

## Boundaries

An execution graph describes what a runtime did: tasks, calls, retries, and control flow. An
Assurance Graph describes why an assurance statement may be trusted: provenance, external effects,
evidence, dependency relationships, and claim limitations. It does not schedule, authorize, retry,
or execute anything.

It is also not GraphRAG or a general knowledge graph. It has no retrieval index, embeddings,
ontology completion, natural-language inference, or open-world fact store. An LLM may help a human
draft a candidate, but observed graph elements must be bound to artifacts and inferred relations
must remain explicitly inferred; LLM guesses alone are not graph evidence.

The graph is never the source of truth. Source artifacts and their digests are authoritative because
graphs are derived, can be regenerated, and can become stale. A verifier rejects missing source
references and digest mismatches rather than silently repairing the graph.

## Shared fate and invalidation

`depends_on` connects a claim or attempt to a dependency. `shares_fate_with` connects dependencies
that fail through a common boundary. The verifier does not infer independence from two names or two
providers: when shared fate is present, the related claim remains `NOT_DEMONSTRATED`.

`invalidates` connects a changed or revoked dependency/evidence node to a claim or attestation. A
graph containing that edge produces a stale/`NOT_DEMONSTRATED` claim disposition. A future profile
version may add signed dependency snapshots; v0alpha1 intentionally does not turn graph topology
into a deployment decision.

## Verification is not demonstration

`GRAPH_VERIFIED` means that the graph schema, references, digests, duplicate constraints, and
provenance rules are internally valid and reproducible. It does not mean that a recovery capability
was demonstrated. Inferred support, shared-fate dependencies, invalidation, or missing observed
evidence keep claim support at `NOT_DEMONSTRATED`. `PACKET_VERIFIED` in the existing v0alpha2
transactional-action verifier remains independent and retains its existing meaning.

## Non-goals

- no Neo4j or graph database;
- no GraphRAG or search service;
- no LangGraph or execution runtime;
- no authorization/control plane;
- no automatic `SUPPORTED` promotion or new graph score;
- no human-drill execution or claim that a drill occurred.
