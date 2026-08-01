# Delegation Resilience Reference Model

## Scope

本モデルの対象は、単体のmodelやagentではなく、AIへ仕事を委譲した社会技術的業務システムです。

```text
stakeholders
    ↓ expectations / rights / harms
mission owner ──delegates──> agent/workflow ──acts──> external system
      ↑                              │                    │
      └── accountability             ├── evidence         └── outcome
                                     └── handover/fallback
```

## Core objects

### ConstitutionalConstraints

Missionや業務上のrisk appetiteより上位の制約です。

- applicable law and regulation
- fundamental rights
- safety limits
- prohibited harms and actions
- non-delegable decisions
- final accountable organization and roles

### MissionSpec

守る対象をagentの稼働ではなくstakeholder outcomeとして記述します。

- mission ID and owner
- beneficiaries and affected parties
- acceptable outcomes
- critical functions
- impact tolerances
- sacrifice decisions and priority rules
- review and expiry

### ActionProfile

外部副作用を持つactionの意味を定義します。

- stable action ID
- required authority
- target and blast-radius dimensions
- native idempotency support
- irreversible point
- outcome probe
- compensation semantics
- retry classification
- data sensitivity

`compensation`はrollbackではありません。新しい副作用を持つ別のactionとして扱います。

### DelegationGrant

誰が、誰へ、何を、どの範囲・期限で委譲したかを表します。

- delegator and delegatee identities
- mission and action scope
- quantitative limits
- validity interval
- policy generation
- approval and revocation conditions
- subdelegation depth and narrowing rules

Human identity、workload identity、agentの表示名を混同しません。

### AdaptiveEnvelope

現場が変動へ対応するために変更できる範囲を定義します。

- adaptable practices
- triggering conditions
- hard boundaries
- required evidence during adaptation
- time limit and expiry
- recovery/re-entry criteria
- authority to make permanent changes

### RecoveryProfile

- safe state
- capability-specific degraded modes
- containment actions
- fallback candidates
- common-mode dependencies
- external reconciliation procedure
- revalidation scope
- recovery owner

Fallbackは`configured`と`qualified`を区別します。所定のexerciseに成功するまでqualifiedとはみなしません。

### EvidenceProfile

- required precondition evidence
- required post-action observations
- authoritative external source
- integrity and custody requirements
- freshness
- independence/shared fate
- confidentiality and retention
- acceptable unknowns

### ExerciseSpec and Attestation

`ExerciseSpec`はinject、前提、観測範囲、合格条件を定義します。実測結果は契約本文へ書き戻さず、署名付き`Attestation`として保存します。

Attestationには次を含めます。

- scenario and assumptions
- system and contract versions
- observed outcomes
- timing and exposure
- human participation conditions
- evidence gaps
- residual weaknesses
- issuer and validity

### LearningDecision

- observation type: failure、near miss、adaptation、everyday success、control false positive
- Work-as-Imaginedと観測された仕事の差
- proposed organizational or technical change
- affected stakeholders
- experiment and rollback
- approval
- expected and unintended effects
- follow-up measurement

## Clause effect classes

すべての条項へ実効性classを付けます。

| Class | Meaning |
|---|---|
| `ENFORCEABLE` | policy enforcement pointで決定的に強制できる |
| `OBSERVABLE` | 独立したsourceまたは外部状態から確認できる |
| `EXERCISABLE` | 限定条件下のexerciseで検証できる |
| `ASSERTED` | ownerによる宣言であり、自動検証されていない |
| `UNSUPPORTED` | 現在の構成では保証・観測できない |

Critical claimが`ASSERTED`または`UNSUPPORTED`の場合は、少なくとも明示的なwarningとrisk acceptanceを要求します。

## Runtime epistemic state

外部actionの結果を二値化しません。

```text
NOT_STARTED
PREPARED
COMMITTING
CONFIRMED_SUCCEEDED
CONFIRMED_FAILED
OUTCOME_UNKNOWN
PARTIALLY_EXECUTED
COMPENSATED
IRREVERSIBLY_EXECUTED
```

基本規則は次の通りです。

- timeoutは`CONFIRMED_FAILED`ではなく`OUTCOME_UNKNOWN`。
- `OUTCOME_UNKNOWN`をblind retryしない。
- external reconciliationを先に行う。
- unknownの間はimpact reservationを解放しない。
- idempotencyのない不可逆actionはautomatic retryしない。

## Resilience states

`NORMAL / DEGRADED / HALTED / RECOVERING`はmissionの表示状態として利用できますが、内部状態を一つに潰しません。

- dependency health
- capability state: read、propose、approve、commitなど
- individual action outcome
- recovery episode
- evidence confidence
- mission state

状態はglobalではなく、`mission × capability × dependency`単位で扱います。

## Shared fate

独立性を主体数やmodel数だけで判断しません。

- model family and provider
- cloud account and region
- identity provider、IAM、KMS
- network and DNS
- policy distribution
- database and queue
- prompt and template
- retrieval source and external oracle
- connector implementation
- operator and on-call team

未知の依存関係をindependentとして扱いません。
