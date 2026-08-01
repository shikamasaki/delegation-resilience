# Assurance Model

## Purpose

Delegation Resilienceは、未知の変動を含む社会技術システムについて普遍的な安全や回復を証明しません。定義されたclaimを、限定された条件、証拠、exercise、残存不確実性と結び付けます。

## Claim structure

```text
Claim
├─ scope and validity period
├─ stakeholders and unacceptable harms
├─ argument
├─ evidence references
├─ exercise attestations
├─ assumptions and dependencies
├─ known gaps
└─ residual uncertainty
```

例：

> 返金agentのmodelが停止しても、自動返金を停止し、15分以内に必要情報と権限を伴ってhuman queueへ引き継ぎ、正当な要求を24時間以内に解決し、二重返金を発生させない。

このclaimは、宣言したprovider、workflow、staffing、exercise条件の範囲に限られます。Queueへの移送だけをrecoveryとはみなしません。

## Acceptability axes

Recovery claimは、次を別々に評価します。

- `constraint_integrity`: 非交渉制約、harm ceiling、contestabilityを維持したか
- `mission_adequacy`: critical functionとimpact toleranceを満たしたか

Domain Profileは必要に応じてdistributional、cognitive、physical impactを追加します。停止による二次的危害もmission adequacy側で観測します。

## Evidence semantics

Evidence eventは、少なくとも次を区別します。

- `asserted`: 当事者またはsystemによる申告
- `observed`: sourceから直接観測した記録
- `inferred`: 複数の記録から導出した判断
- `reconciled`: 外部のauthoritative stateと突合済み

完全性、真正性、正しさは別の性質です。

- hash chainは事後改変の検知を支援する。
- signatureは署名主体を示す。
- external reconciliationは外部結果との一致を確認する。
- いずれも、目的の妥当性やsource自身の正しさを単独では保証しない。

## Assurance mechanisms

一つのclaimは、次の複数mechanismで同時に支えられます。

- `ENFORCEABLE`: policy enforcement pointで強制する
- `OBSERVABLE`: 独立sourceまたはexternal stateから観測する
- `EXERCISABLE`: 限定条件下で実際に演習する

Mechanismの存在と、現在のsupport statusを混同しません。Supportは`ASSERTED / SUPPORTED / CONTRADICTED / UNKNOWN`、deployment判断は`PERMITTED / PERMITTED_WITH_ACCEPTANCE / PROHIBITED`として別に記録します。

## Exercise semantics

Exerciseの結果は、次の形式で表現します。

- `demonstrated`: 記載された条件で達成した
- `not_demonstrated`: 達成を確認できなかった
- `failed`: 定義された条件を逸脱した
- `inconclusive`: 観測や環境の問題で判断不能

`passed`を普遍的なresilience保証として扱いません。

Attestationは少なくともexercise mode、開始・終了時刻、system under testとversion、実際のfault scheduleとload、shared dependencies、human participation、structured measurements、evidence gapを保持します。

同一要件に対する複数のevidence observationは別々のobservation IDを持ちます。同じmeasurement、fault、component、claim resultもIDまたはclaim参照によって一意にし、矛盾する値を一つのAttestation内で併記しません。

証拠強度には上限があります。

- deterministic simulationはtechnical state transitionを検証できるが、実在する人間のtakeover capabilityを実証できない。
- tabletopはroleやdecision pathを調べられるが、RecoveryClaim全体や実権限、操作access、処理能力を`demonstrated`にできない。
- sandboxはproduction-equivalentな権限・依存・loadとの差を残存不確実性として記録する。
- live drillとproduction-like exerciseも、観測範囲外へ結果を一般化しない。

`result: demonstrated`にはRecoveryClaimの`requiredCapabilities`をすべて満たす測定とevidenceを必要とします。部分的な能力だけを確認した場合、確認した能力は記録してもclaim全体は`not_demonstrated`です。

最低限のscenario familyは次です。

- model/tool/provider outage
- external success followed by response loss
- partial execution
- stale policy or credential revocation
- missing approver
- fallback privilege mismatch
- common-mode identity/data dependency failure
- evidence collector outage
- human takeover timeout
- control/assurance plane outage

## Outcome measures

単一scoreへ集約せず、条件付きvectorとして扱います。

- Time to Detect
- Time to Contain
- Time to Recover to an acceptable state
- maximum irreversible exposure
- fallback activation and qualification
- external reconciliation success
- human takeover time and task success
- evidence reconstruction success
- stale、missing、unknown evidence
- substitutability and shared-fate profile
- remediation-to-retest lead time

各測定値には、scenario、分母、観測期間、exerciseか実事故か、unknown、測定限界を付けます。

## Human capability safeguards

- 個人のperformance rankingに使用しない。
- drill結果を懲罰へ利用しない。
- team-levelのcritical task capabilityを評価する。
- participantへ目的、data use、retentionを説明する。
- workload、information、time、authorityを結果と併記する。
- AIのみを重大なhuman performanceのjudgeにしない。

## Regulatory mappings

出力は`Evidence-to-Control Mapping`であり、認証や法的判断ではありません。

- framework and version
- applicability assumptions
- control requirement
- evidence references
- freshness and issuer
- coverage、gap、confidence
- human assessor

ISO、NIST、法令へ対応する場合も、mappingとconformity assessmentを区別します。
