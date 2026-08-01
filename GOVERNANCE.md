# Governance

## Current phase

本projectはmaintainer-led incubationです。仕様の普及より、概念の妥当性と異なる領域での再現性を優先します。

## Decision principles

変更は次の順序で評価します。

1. 法令、権利、安全上の制約を弱めないか
2. claimを検証済み以上に見せないか
3. unknownとresidual uncertaintyを保持しているか
4. 現場の適応能力を不必要に奪わないか
5. 特定vendorへのlock-inやcommon-mode failureを増やさないか
6. 二つ以上のdomainで意味を保てるか
7. 実装・exercise・evidenceで反証可能か

## Specification maturity

- `exploratory`: 用語・例・反例を収集中
- `working-draft`: 実装可能だが互換性保証なし
- `candidate`: 二つ以上のdomainと独立実装で検証済み
- `stable`: governance、互換性、conformance policyを公開済み

現在のstatusは`exploratory`です。

## Conflicts of interest

将来、商用製品が本仕様を実装しても、そのvendorが単独で適合認証者になるべきではありません。evidence generation、assessment、certificationを可能な限り分離します。
