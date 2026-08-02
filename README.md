# Delegation Resilience

> Repeatable recovery assurance for AI delegation.

Delegation Resilience（委譲レジリエンス）は、AIへ作業・判断・限定された実行権限を委譲する社会技術的業務システムが、法令・権利・安全上の制約を維持しながら、変動や異常の下でも許容可能な成果と組織的accountabilityを保ち、必要に応じて安全に拒否・停止・縮退・復旧し、実際の仕事から適応能力を高めるための考え方です。

このリポジトリは、特定製品のコードベースではありません。共通思想、参照モデル、assurance model、実証方法を公開し、複数のvertical productで検証するためのincubation repositoryです。

## Core thesis

AIそのものを完全に信頼できるようにするのではなく、AIを完全には信頼できなくても、人間と組織が許容可能な成果、介入権、説明責任、回復能力を失わないようにします。

既存のagent governance、AI risk management、operational guidanceも、business outcome、human handoff、fallback、failure exercise、continuous improvementを扱っています。Delegation Resilienceはそれらを置き換えるものではありません。

- mission単位の限定されたrecovery claim
- 外部結果について何が分かっているかというepistemic state
- fallbackとhuman takeoverのqualification
- claimを支える証拠のmechanismと強度
- exercise attestationと残存不確実性

を一つのvendor-neutralなassurance lifecycleへ結び、次を問います。

> 失敗したとき、委譲された業務はimpact tolerance内へ本当に回復できるか。人間や代替系は本当に引き継げるか。それを限定条件付きの証拠として反復可能に示せるか。

## The model

```text
Constitutional constraints
          ↓
Acceptability decision
          ↓
Mission, stakeholders and delegation boundary
          ↓
Domain profile and adaptive envelope
          ↓
Evidence → exercise → external reconciliation
          ↓
Containment → handover → recovery → revalidation → learning
```

本構想では、次を明確に分離します。

- `Contract`: どう動くべきか。Work-as-Imagined。
- `Evidence`: 何が記録・観測されたか。Work-as-Recorded。
- `Assurance Case`: なぜ限定された回復主張を信じるのか。
- `Exercise Attestation`: どの条件・時点で何が実証されたか。
- `Learning Decision`: 経験を受け、組織や仕組みをどう変更したか。

## Principles

1. モデルではなく、stakeholderへ提供する成果を守る。
2. 能力と権限を分離し、権限には由来・範囲・期限を持たせる。
3. Missionより法令・権利・安全上の制約を上位に置く。
4. 安全な拒否・停止・目標放棄もresilient outcomeとして認める。
5. 外部結果に関するepistemic `UNKNOWN`と部分観測を第一級状態として扱う。
6. fallbackは設定ではなく、演習済みの能力として扱う。
7. human oversightを情報・時間・技能・権限・実行手段で評価する。
8. failureだけでなく、near miss、everyday success、現場適応から学ぶ。
9. 単一のresilience scoreを作らない。
10. 製品自身の停止・誤判定・侵害も設計と演習の対象にする。

詳しくは[Manifesto](docs/manifesto.md)と[Reference Model](docs/reference-model.md)を参照してください。

## Product strategy

思想は水平ですが、実証は狭いverticalから始めます。

- [OrgForge](https://github.com/shikamasaki/orgforge-plugin): agentic software deliveryにおける最初のreference implementation
- Recovery Assurance experiments: 外部状態を変更するAI workflowのgame day、外部結果照合、human takeover
- Future vertical packs: customer operations、finance、public sectorなど。実証前には一般化しません。

思想と実装範囲を次の二層に分けます。

```text
Delegation Resilience Doctrine
├─ Universal Core
│  ├─ constitutional constraints and acceptability
│  ├─ delegation boundary and accountability
│  ├─ intervention and uncertainty
│  ├─ recovery claims and evidence
│  └─ learning
└─ Domain Profiles
   ├─ Transactional Action
   ├─ Knowledge Work
   ├─ Human Decision Support
   └─ Physical / Safety-Critical
```

現時点で機械可読形式とrunnerの対象にするのは`Transactional Action`だけです。思想の普遍性とsoftware kernelの再利用性を混同しません。

最初から独自IAM、policy engine、workflow runtime、observability backendを再実装しません。OPA/Cedar、既存IAM、OpenTelemetry、durable execution基盤へ投影し、Delegation Resilience固有の意味と保証ループに集中します。

## Repository contents

- [Manifesto](docs/manifesto.md): 問題設定、定義、原則、境界
- [Reference Model](docs/reference-model.md): 共通概念とライフサイクル
- [Universal Core](docs/universal-core.md): 全domainに共通する最小概念
- [Assurance Model](docs/assurance-model.md): claim、evidence、exercise、不確実性
- [State Model](docs/state-model.md): intent、attempt、epistemic outcome、external effectの分離
- [Landscape and References](docs/landscape.md): 標準、研究、関連製品との境界
- [Transactional Action Profile](profiles/transactional-action/README.md): v0alpha aggregateとJSON Schema
- [Roadmap](ROADMAP.md): 12か月の検証計画とspin-out条件
- [ADR-0001](docs/decisions/0001-incubate-before-spinout.md): 思想を独立させ、製品分離を遅らせる理由
- [Refund example](examples/refund/README.md): 最初の非coding reference scenario
- [Refund Recovery Game Days](game_days/refund/README.md): response loss比較、shared-fate検出、human takeover preflight
- [Facilitated human drill runbook](game_days/refund/HUMAN_DRILL.md): 実地演習の前提、測定、証拠、fail-closed判定
- [Portable Verification](docs/portable-verification.md): DSSE、in-toto manifest、外部trust policy、dependency invalidation、standalone verifier
- [ADR-0002](docs/decisions/0002-portable-verification-boundary.md): 署名と検証の信頼境界

## Status

`incubating / v0alpha1 semantic kernel complete / v0alpha2 portable verification`

v0alpha1のprofileとexercise semanticsは機能凍結し、v0alpha2では後方互換なportable verification layerを追加しています。現在のreference bundleは、DSSE envelopeと全subject bytesからなる同じpacket、verifier code/environment digest、評価時点、外部trust policy、consumer high-watermarkから同じ限定的な`VerificationResult`をofflineで再現します。これは独立認証ではありません。`PACKET_VERIFIED`はclaim supportやdeployment可否を意味しません。

ここで公開する語彙と形式は、現時点では国際標準、認証、規制適合を意味しません。少なくとも二つの異なる業務領域と複数の独立実装で有効性を確認するまでは、`standard`ではなく`working model`または`v0.x format`と呼びます。

## Non-goals

- AIの安全性や正しさを普遍的に保証すること
- 証拠量をresilienceの代理指標にすること
- ログからWork-as-Doneを完全に復元すること
- human-in-the-loopという表示だけで人間統制を主張すること
- すべての外部操作をrollback可能と主張すること
- 法令・標準へのmappingを認証や法的助言として提供すること
- 人間の個人評価や懲罰にdrill・ledgerを利用すること

## Contributing

現在は問題定義と実証可能性を優先しています。新しい機能案より、反例、実事故・near miss、失敗したfallback、測定不能なclaim、既存標準との重複を歓迎します。[CONTRIBUTING.md](CONTRIBUTING.md)を参照してください。

## License

Apache License 2.0. See [LICENSE](LICENSE).
