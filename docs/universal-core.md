# Universal Core

## Purpose

Universal Coreは、transaction処理、knowledge work、人間の意思決定支援などに共通する最小の問いを定義します。domain固有のfailure semanticsや実行protocolを一つへ統一しません。

## 1. Constitutional integrity

法令、権利、安全、許容不能な危害、非委譲decision、最終accountabilityをmissionより上位に置きます。これらは通常のbusiness risk acceptanceと同じ手続きで免除できません。

## 2. Acceptability

「許容可能」を誰が、誰の利益と負担を考慮して決めたかを問い、次を区別します。

- `constraint_integrity`: 非交渉制約を守ったか
- `mission_adequacy`: 必要最低限の成果を提供したか
- domain-specific impact dimensions: distributional、cognitive、physicalなど

比較baselineはno-AIに限定せず、current workflow、lower autonomy、alternative system、non-performanceを含むfeasible alternativesから選びます。

## 3. Delegation boundary

Taskと限定authorityは委譲できますが、組織のaccountability、法的liability、救済責任がagentへ移転したとはみなしません。

- delegator and delegatee
- purpose and task scope
- authority and limits
- validity and revocation
- subdelegation
- non-delegable decisions

## 4. Intervention and adaptive envelope

介入権をkill switchの有無だけで評価しません。人間または別systemが必要なinformation、time、competence、authority、actionabilityを持つかを扱います。

規則どおりに動けない状況へ対応するため、変更可能範囲、hard boundary、必要証拠、expiry、re-entry、恒久化のdecision rightを定義します。

## 5. Uncertainty

不確実性をfailureへ潰しません。

- known and confirmed
- unknown
- conflicting evidence
- partially observed
- unsupported claim
- residual uncertainty

Domain Profileは、この共通語彙を具体的なepistemic stateへ落とします。

## 6. Recovery claim

Recoveryは元の状態へ戻すことだけではありません。

- safe refusal or cessation
- containment
- degradation
- handover
- restoration of acceptable function
- reconciliation
- revalidation before re-entry

Claimにはscope、validity、assumptions、stakeholders、evidence、exercise conditions、known gapsを伴わせます。

## 7. Assurance

Claimを次の独立したartifactで支えます。

- normative contract/profile
- runtime and external evidence
- argument linking evidence to claim
- exercise attestation
- residual uncertainty

一つのclaimはenforcement、observation、exerciseの複数mechanismで支えられます。仕組みが存在することと、claimが支持されたことを区別します。

## 8. Learning

Failureだけでなく、near miss、everyday success、adaptation、control false positiveから学びます。

学習はcontrol追加に限定しません。

- 有効な適応を正式化する。
- 誤検知や害を生むcontrolを弱める、または削除する。
- role、decision right、context flowを変更する。
- 変更後の意図した効果と副作用を再測定する。

## Domain-profile rule

Universal Coreの概念を実装へ落とすとき、各Domain Profileは最低限次を宣言します。

- protected outcome and affected stakeholders
- domain-specific harm dimensions
- delegation and intervention boundary
- failure and uncertainty semantics
- recovery meaning
- evidence sources and limitations
- exercise method
- applicability and non-applicability
