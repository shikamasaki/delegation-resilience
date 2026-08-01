# Delegation Resilience Reference Model

## Scope

本モデルの対象は、単体のmodelやagentではなく、AIへ仕事を委譲した社会技術的業務システムです。思想上の`Universal Core`と、業務固有の`Domain Profile`を分離します。

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

非交渉制約は、証拠不足を理由にrisk acceptanceしてdeploymentできません。

### AcceptabilityDecision

何を「許容可能」と呼ぶかを決定した手続きと根拠を記録します。Mission ownerのrisk appetiteだけでは決定しません。

- decision owner and approvers
- beneficiaries、affected partiesとそのparticipation
- current workflow、no-AI、lower-autonomyを含むfeasible alternatives
- individual and group harm ceilings
- constraint integrity criteria
- mission adequacy criteria
- refusal、delay、cessationが生むsecondary harms
- contestability、review、remedy
- unresolved dissent and representation limits
- validity and review triggers

`constraint_integrity`と`mission_adequacy`を別々に評価します。常に停止するsystemを、missionを果たしていないのにresilientと判定しません。

### MissionSpec

守る対象をagentの稼働ではなくstakeholder outcomeとして記述します。

- mission ID and owner
- beneficiaries and affected parties
- acceptable outcomes
- critical functions
- impact tolerances
- sacrifice decisions and priority rules
- review and expiry

### TransactionalActionProfile

これはUniversal Coreではなく、外部状態をcommitするworkflow向けの最初のDomain Profileです。外部副作用を持つactionの意味を定義します。

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

### RecoveryClaim and RecoveryProfile

RecoveryClaimは、限定されたscopeで何を回復可能と主張するかを表し、次の参照edgeを必須にします。

- `constraintRefs`: claimが支持すべき非交渉制約
- `actionRefs`: claimのscopeに含むaction
- `evidenceRequirementRefs`: claim判定に必要なEvidenceProfile上の要件
- `requiredCapabilities`: `demonstrated`判定に必要な回復能力

RecoveryProfileは、そのclaimを実現する構成を記述します。

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

- exercise mode and exact scenario
- actual fault schedule、load、shared dependencies
- system under testのcomponentとversion
- started/completed time
- structured measurements
- human participation、authority、operational access
- 一意なobservation IDを持つevidence requirementとartifactの対応
- evidence gaps and residual uncertainty
- issuer、validity、evaluated profile digest

`demonstrated`は単なるrunnerの成功ではありません。Claimの`requiredCapabilities`と必要証拠を満たす場合だけ使用します。特にdeterministic simulationとtabletopは、実際の人間のauthority、access、capacityを伴う`human_takeover`の証拠にはなりません。

### LearningDecision

- observation type: failure、near miss、adaptation、everyday success、control false positive
- Work-as-Imaginedと観測された仕事の差
- proposed organizational or technical change
- affected stakeholders
- experiment and rollback
- approval
- expected and unintended effects
- follow-up measurement

## Domain profiles

Universal Coreをdomain固有のfailure semanticsへ具体化します。

| Profile | Primary concerns | Status |
|---|---|---|
| Transactional Action | commit、idempotency、external effect、reconciliation、compensation | v0alpha |
| Knowledge Work | epistemic drift、source quality、deskilling、longitudinal correction | conceptual |
| Human Decision Support | distributional harm、contestability、automation bias、appeal | conceptual |
| Physical / Safety-Critical | physical hazard、safe state、certified control、human factors | out of implementation scope |

Domainごとにschemaとrunnerを共有できるとは仮定しません。共有するのはUniversal Coreのclaim、accountability、uncertainty、evidence、learning semanticsです。

## DelegationResilienceProfile v0alpha

Transactional Action向けのaggregate rootは、versioned artifactへの参照をまとめます。

```text
DelegationResilienceProfile
├─ exactly 1 MissionSpec
├─ exactly 1 AcceptabilityDecision
├─ 1..n TransactionalActionProfiles
├─ 1..n DelegationGrants
├─ 1..n RecoveryClaims
├─ exactly 1 EvidenceProfile
├─ 0..n ExerciseSpecs
└─ 0..n Attestation references
```

実測値をprofileへ書き戻しません。Inline artifactはstable IDとversionを持ち、aggregate profileをcanonicalizeしてcontent digestを作ります。Attestationは評価したprofile digestを参照します。具体形式は[Transactional Action Profile](../profiles/transactional-action/README.md)で定義します。

## Assurance mechanisms and disposition

`ENFORCEABLE / OBSERVABLE / EXERCISABLE`は排他的classではありません。一つのclaimを複数mechanismで支えられます。

| Axis | Values |
|---|---|
| assurance mechanisms | `ENFORCEABLE`、`OBSERVABLE`、`EXERCISABLE`の集合 |
| support status | `ASSERTED`、`SUPPORTED`、`CONTRADICTED`、`UNKNOWN` |
| deployment disposition | `PERMITTED`、`PERMITTED_WITH_ACCEPTANCE`、`PROHIBITED` |

非交渉制約が`SUPPORTED`でない場合、またはcontradicting evidenceがある場合の既定値は`PROHIBITED`です。risk acceptanceの可否は、制約ごとに明示します。

## Runtime state

Intent、attempt、knowledge、external effect、reconciliation、compensationは別の状態機械です。完全な定義は[State Model](state-model.md)を参照してください。

```text
intent:         REGISTERED → PREPARED → AUTHORIZED → COMMIT_REQUESTED
                → CLOSED_NO_EFFECT | CLOSED_WITH_EFFECT
                REGISTERED | PREPARED | AUTHORIZED → CANCELLED_PRE_COMMIT
attempt:        STARTED → ACKNOWLEDGED | TIMED_OUT | ABORTED
epistemic:      UNKNOWN | CONFIRMED_SUCCEEDED | CONFIRMED_FAILED | PARTIAL
external:       NONE | APPLIED | PARTIALLY_APPLIED | REVERSED
reconciliation: NOT_REQUIRED | PENDING | MATCHED | MISMATCHED | SOURCE_UNAVAILABLE
```

基本規則は次の通りです。

- timeoutは`CONFIRMED_FAILED`ではなくepistemic `UNKNOWN`。
- epistemic `UNKNOWN`をblind retryしない。
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
