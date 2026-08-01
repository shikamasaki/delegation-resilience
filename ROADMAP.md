# Roadmap

## Decision

Delegation Resilienceの思想と参照モデルは今すぐ公開します。水平kernelはOrgForgeと非coding workflowでincubateし、別の商用製品・ブランド・GTMは反復可能な有償需要が確認された後にspin outします。

```text
Build now:      doctrine and falsifiable reference model
Incubate:       shared recovery-assurance kernel
Validate with:  OrgForge + one noncoding workflow family
Spin out when:  portability, repeated value, buyer and budget are proven
```

このロードマップの数値は市場統計ではなく、構想を自己正当化し続けないための内部decision gateです。

## Phase 0 — Foundation and buyer gate（0–2か月）

### Deliverables

- [ ] ManifestoとReference Model v0.1への外部review
- [ ] terminology、non-goals、anti-claimsの確定
- [x] Universal CoreとTransactional Action Profileの分離
- [x] `AcceptabilityDecision`と二軸の評価model
- [x] `DelegationResilienceProfile v0alpha1`のJSON Schema
- [x] intent、attempt、epistemic outcome、external effect、reconciliation、compensationの状態分離
- [x] machine-readable Refund profileの初期instance
- [x] profile内参照graphとcore assurance semanticsのvalidator
- [x] exercise mode、実測条件、証拠強度を持つAttestation schema
- [ ] canonicalizationとdigestのreference implementation
- [ ] scenario taxonomyとevidence envelopeの外部review
- [ ] AWS/NIST/ISOとのclaim-level差分表のreview
- [ ] OrgForge reviewer-outage exerciseの設計
- [x] 非codingの最初のreference workflowとしてRefundを選択

### Discovery gate

初期ICPを、外部状態を変更するB2B agentを企業へ提供しているvendor/SIへ絞ります。

- qualified interview: 20件
- productionまたはproduction-like agentの具体例: 10件以上
- 過去12か月のnear miss、停止、引継ぎ不安の具体例: 5件以上
- budget ownerと既存budget lineの確認: 3件以上
- 有償design partner: 2社以上。無償PoCとLOIは含めない

有償design partnerを確保できない場合、別製品化を停止し、OrgForgeの設計思想として継続します。

## Phase 1 — Recovery Game Day wedge（3–5か月）

### Build

- [ ] v0alpha validatorのdependency・digest・invalidation lint rules
- [ ] local deterministic exercise runner
- [ ] fake model/tool/approver/evidence sink
- [ ] epistemic `UNKNOWN`とexternal reconciliation
- [ ] capability-specific degradation
- [ ] fallback qualification
- [ ] signed exercise attestationとevidence packet
- [ ] OrgForgeでのend-to-end dogfood

### Exercise scenarios

- model/tool outage
- external success after response loss
- partial success
- approver unavailable
- stale policy
- fallback privilege mismatch
- evidence collector outage
- shared IAM/data dependency failure
- human takeover timeout
- assurance plane outage

### Value gate

- 同じofferingの有償game day: 3件
- 既存log/evalだけでは分からなかったmaterial gap: 各案件1件以上
- remediationからretestまで完了: 2社以上
- 初期接続: 5営業日以内
- 案件固有code: 30%未満
- releaseまたは四半期での再実行希望: 2社以上

満たさない場合、SaaSではなくconsulting offeringまたはOrgForge moduleとして扱います。

## Phase 2 — Portability and repeatability（6–8か月）

### Open v0.x

- [ ] design-partner evidenceを反映したprofile/schema revision
- [ ] stable scenario DSL
- [ ] portable local runner
- [ ] versioned evidence envelope
- [ ] adapter SPI
- [ ] conformance and negative test corpus

### Managed capabilities

- [ ] fleet scheduling
- [ ] evidence custody and retention
- [ ] SSO/RBAC
- [ ] exercise history and remediation/retest linkage
- [ ] evidence-to-control mapping preview

### Repeatability gate

- OrgForge以外の非coding workflow 2社で同じschema/runnerを使用
- 3社中2社が年間または反復契約へ移行
- evidenceが少なくとも1社のsecurity/risk reviewで実際に利用される
- custom codeを継続的に減らせる

この段階でも、central inline control planeは作りません。

## Phase 3 — Separate-product decision（9–12か月）

次の条件をすべて満たした場合のみ、新ブランド、新repository、独立GTMを検討します。

1. 有償利用5組織以上、そのうち非OrgForge・非codingが3社以上
2. recurring契約3社以上
3. 共通するeconomic buyerとbudget lineが商談の60%以上
4. 一つのworkflow packで導入作業の70%以上を共通化
5. 顧客固有codeが20%以下
6. 2回以上drillを行う顧客が過半数
7. exerciseが具体的remediationを生み、retestで回復能力が改善
8. 既存platform bundleでは不足する理由を顧客自身が説明できる

### Decision outcomes

- 全条件を満たす: horizontal productとしてspin out
- codingでのみ成立: OrgForgeのresilience capabilityとして継続
- Passportまたは単発drillのみ売れる: assurance serviceとして扱う
- buyer不明、paid demand不足、custom code 30%以上: product investmentを停止

## Initial product boundary

### Build or integrate

- claim/evidence/exercise lifecycle
- external outcome reconciliation
- recovery state and revalidation
- shared-fate analysis
- human takeover exercise
- policy/evidence adapters

### Do not build initially

- 独自IAM
- 独自policy engine
- 独自durable execution platform
- 汎用observability backend/UI
- universal browser proxy
- blockchain ledger
- automatic compliance certification
- single resilience score
- human performance ranking
- AI judgeによる重大操作の最終承認
- medical、physical controlへの展開
- central control planeを全操作の必須同期経路にすること

## External risks to monitor

- MCP/A2Aがdelegation、reversibility、recovery semanticsを標準化する
- major cloudやenterprise platformがhuman takeoverとscenario testingをbundleする
- evidence mappingだけが購買理由となり、recoverabilityが利用されない
- exerciseが一度きりの監査行事となり、継続改善へ接続しない
- detailed evidenceがworker surveillanceや懲罰へ転用される
