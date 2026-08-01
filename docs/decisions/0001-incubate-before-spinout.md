# ADR-0001: Incubate the kernel before product spin-out

- Status: accepted
- Date: 2026-08-01

## Context

Delegation Resilienceはsoftware deliveryを超える思想ですが、horizontal control plane、agent authorization、observability、GRC reportingには既存製品があります。また、第二の業務領域で検証していない共通kernelの抽出はpremature abstractionになります。

OrgForgeは、agentic software deliveryにおける具体的なGoal、role、phase gate、independent review、evidence、degradation、recoveryを持ち、最初の実証環境として利用できます。

## Decision

- 思想とreference modelは独立した本リポジトリで公開する。
- 実装kernelは当面OrgForgeでdogfoodする。
- 非coding workflowで同じ概念とrunnerを有償検証する。
- portability、repeatability、buyer、budgetが確認されるまで別商用製品へspin outしない。

## Consequences

### Positive

- 思想をOrgForge固有の語彙へ閉じ込めない。
- 実装前に境界とanti-claimsをreviewできる。
- 失敗してもOrgForgeのresilience capabilityとして資産が残る。
- 第二domainから得た事実に基づいて共通APIを設計できる。

### Negative

- 独立カテゴリとしての認知獲得は遅くなる。
- 当初は仕様と実装が別repositoryに分かれる。
- OrgForge固有の仮定がreference modelへ漏れ込む可能性がある。

## Revisit conditions

ROADMAPのPhase 3 gateを満たしたとき、または既存標準・platformによって前提が大きく変化したときに再検討します。
