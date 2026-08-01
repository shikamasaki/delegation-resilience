# Transactional Action Profile v0alpha1

## Status

`exploratory / incompatible changes expected`

外部状態をcommitするAI workflow向けの最初のDomain Profileです。Universal Core全体を標準化するものではありません。

## Aggregate

`DelegationResilienceProfile`は次をinlineで保持します。

- exactly one `MissionSpec`
- exactly one `AcceptabilityDecision`
- one or more `TransactionalActionProfile`
- one or more `DelegationGrant`
- one or more `RecoveryClaim`
- exactly one `EvidenceProfile`
- zero or more `ExerciseSpec`
- zero or more external `ExerciseAttestation` references

Attestationは実測結果であり、profile本文へ埋め込みません。

## Schemas

- [Aggregate profile](schema/profile.schema.json)
- [MissionSpec](schema/mission.schema.json)
- [AcceptabilityDecision](schema/acceptability-decision.schema.json)
- [TransactionalActionProfile](schema/action-profile.schema.json)
- [DelegationGrant](schema/delegation-grant.schema.json)
- [RecoveryClaim](schema/recovery-claim.schema.json)
- [EvidenceProfile](schema/evidence-profile.schema.json)
- [ExerciseSpec](schema/exercise.schema.json)
- [ExerciseAttestation](schema/attestation.schema.json)
- [ExerciseEvidence](schema/exercise-evidence.schema.json)
- [HumanDrillEvidence](schema/human-drill-evidence.schema.json)
- [Human drill preflight](schema/human-drill-preflight.schema.json)
- [Runtime state snapshot](schema/runtime-state.schema.json)

Schemas use JSON Schema Draft 2020-12. YAMLはauthoring convenienceであり、duplicate keyを拒否してJSON data modelへ変換してから検証します。

## Two-stage validation

v0alpha1への適合確認は、JSON Schemaだけでは完了しません。構造検証とcross-artifact意味検証の両方を実行します。

```bash
python3 -m pip install -r requirements-validation.txt
check-jsonschema --schemafile profiles/transactional-action/schema/profile.schema.json examples/refund/profile.yaml
python3 tools/validate_profile.py examples/refund/profile.yaml
python3 tools/validate_profile.py examples/refund/profile.yaml \
  --attestation examples/refund/game-day/attestation.yaml \
  --artifact-root . --as-of 2026-08-03T00:00:00Z
```

JSON Schema単独で通過したdangling referenceやunsupported deploymentを、valid profileとして扱いません。CIは両方を必須stepとして実行します。

JSON Schemaは構造とcardinalityを検証します。[Semantic validator](../../tools/validate_profile.py)は、現時点で次を検証します。

- artifact ID、action ID、claim IDのuniqueness
- `actionRefs`と`claimRefs`が同じprofile内に存在すること
- `constraintRefs`と`evidenceRequirementRefs`が同じprofile内に存在すること
- すべてのconstitutional constraintが少なくとも一つのRecoveryClaimから参照されること
- `SUPPORTED`でないRecoveryClaimが`PROHIBITED`であること
- Attestationのclaimがscenarioの対象であること
- Attestationのclaim、measurement、fault、component、evidence observation IDの一意性
- Attestationのscenario、claim、measurement、evidence参照
- Attestationの`evaluatedProfile.digest`がRFC 8785 canonical profile digestと一致すること
- Attestationのevidence artifactと宣言されたSUT artifactが、明示したartifact root内のlocal bytesへ解決でき、SHA-256 digestと一致すること
- exercise evidenceが`ExerciseEvidence` envelopeであり、scenario、environment、issuer、観測時刻、requirement、findingが外側のAttestation observationと一致すること
- 各`demonstratedCapabilities`が`capabilityEvidence`で個別のmeasurementとevidence requirementへ束縛されること
- built-in deterministic runnerの技術的部分能力は、同じprofileから再生成したartifactとのbyte-for-byte一致がある場合だけ昇格できること
- `demonstrated`がclaimのrequired capabilityとevidenceを満たすこと
- `demonstrated`が参照するevidence observationの`finding`が`satisfied`であること
- deterministic simulationだけでRecoveryClaim全体を`demonstrated`にしないこと
- `handover`と`human_takeover`にparticipant単位のqualification、authority、operational-access artifactがあり、Attestationから解決したlocal bytesのdigestと一致すること
- Attestationの時刻順序とexpiry

同じevidence requirementを時刻やsourceを変えて複数回観測することは許可します。その場合も各観測は一意な`evidenceObservationId`を持ち、異なる値を同じIDで上書きできません。各観測は`finding: satisfied | contradicted | unavailable | inconclusive`を持ちます。Negative observationもevidenceですが、requirementを満たした証拠ではありません。

Human evidenceは`HumanDrillEvidence` envelopeで、scenario、sandbox environment、participant、evidence type、対象、issuer、観測時刻、期限をartifact内部にも保持し、scenarioの`humanEvidenceBindings`および外側の参照と照合します。現段階の`assurance: digest_bound`は内容の完全性と内部整合性を示すだけで、issuer真正性を示しません。署名・trust store検証は未実装であるため、v0alpha1 validatorは`handover`と`human_takeover`の能力実証への昇格を常に拒否します。

Technical evidenceもdigest一致だけではpositive assuranceとして扱いません。v0alpha1で技術的部分能力を昇格できるのは、validatorが明示的に知るbuilt-in deterministic runnerを同じprofileで再実行し、参照artifactが再生成bytesと一致する場合だけです。未知のrunnerや自己申告envelopeは、構造と完全性を検証できても能力を昇格できません。

`sharedDependencies`は、`dependencyAnalysisRequired`がないscenarioでは条件を表すlabelです。`dependencyAnalysisRequired: true`の場合だけ、`dependencyTopology`が必須となり、shared dependencyとfault targetをcomponent参照として検証します。

次はまだ後続linterの対象です。

- recovery claimのdependency IDと実際のconfigurationの対応
- 複数claimを束ねたdeployment全体のdisposition導出
- dependency変更に伴うAttestationの自動失効

## Canonicalization and digest

署名・参照用digestは、次の手順で作ります。

1. YAML inputの場合、duplicate keyと非JSON typeを拒否してJSON data modelへ変換する。
2. 対応するv0alpha schemaで検証する。
3. RFC 8785 JSON Canonicalization Schemeでcanonicalizeする。
4. canonical bytesへSHA-256を適用し、`sha256:<lowercase-hex>`で表現する。

Artifact自身へ自己参照digestを埋め込みません。Attestation、evidence、manifestが評価対象artifactのdigestを参照します。

## Attestation validity

RecoveryClaimは`assuranceDependencies`を列挙します。model、prompt、tool、policy、grant、connector、outcome source、human role、shared dependencyが変更された場合、対応するAttestationを次のいずれかにします。

- `any_change`: 自動的にstaleへする。
- `manual_review`: assessorがclaimへの影響を判断するまでstale扱いにする。

v0alphaでは変更を自動分類しないため、タグラインは`Continuous`ではなく`Repeatable recovery assurance`とします。

## Enforcement boundary

Schema validationはruntime enforcementではありません。Profileの各claimは、別々に次を宣言します。

- `assuranceMechanisms`: enforcement、observation、exerciseの組合せ
- `supportStatus`: 現在の証拠がclaimをどこまで支持するか
- `deploymentDisposition`: deploymentを許可するか

非交渉制約を支持するmechanismまたはevidenceが不足する場合、`PROHIBITED`を既定とします。

`knownGaps`は解消可能なcontrol・evidence上の不足、`residualUncertainty`は現在のscopeと証拠を前提に残る不確実性を表します。両方を明示し、後者を空欄にすること自体を完全性の主張には使いません。

`AdaptiveEnvelope`はUniversal Coreの概念ですが、v0alpha1の機械可読scopeには含めません。最初のexerciseで実際に必要な調整境界が分かってからschema化します。

## Example

[Refund profile](../../examples/refund/profile.yaml)は、まだexercise attestationを持たないため、recovery claimを`ASSERTED / PROHIBITED`として公開します。実験成功後にのみ`SUPPORTED`へ変更できます。
