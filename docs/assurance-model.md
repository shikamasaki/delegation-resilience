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

> 返金agentのmodelが停止しても、自動返金を停止し、15分以内にhuman queueへ切り替え、二重返金を発生させない。

このclaimは、model停止以外の障害や、15分を超えた後の業務品質まで自動的には含みません。

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

## Exercise semantics

Exerciseの結果は、次の形式で表現します。

- `demonstrated`: 記載された条件で達成した
- `not_demonstrated`: 達成を確認できなかった
- `failed`: 定義された条件を逸脱した
- `inconclusive`: 観測や環境の問題で判断不能

`passed`を普遍的なresilience保証として扱いません。

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
