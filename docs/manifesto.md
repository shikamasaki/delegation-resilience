# Delegation Resilience Manifesto

## Problem

AI agentは回答を生成するだけでなく、送信、更新、削除、購入、承認、公開、コード変更など、外部世界へ副作用を起こします。同時に、その振る舞いはmodel、prompt、retrieval data、tool、provider、組織上の役割分担によって変化します。

このとき問題は「AIが壊れるか」だけではありません。

- AI停止後に、人間が業務を再開できない。
- 同じprovider、IAM、data sourceへ依存したfallbackが同時に停止する。
- 正規権限を持つAIが、誤った目的や情報に基づいて正常に実行する。
- 承認者が情報・時間・技能を持たず、承認が形式化する。
- 外部操作は成功したが応答が失われ、結果不明のまま再実行される。
- 記録は残っていても、実際の外部結果や現場の適応を再構成できない。

AIへ仕事を渡すことで、業務システム全体が脆くなる問題を扱う必要があります。

## Definition

Delegation resilience is the capacity of a socio-technical work system to sustain lawful and acceptable outcomes, accountable control, and recoverability under AI delegation, including safe refusal, degradation, recovery, and evidence-informed adaptation under variability and surprise.

委譲レジリエンスとは、AIへ作業・判断・限定された実行権限を委譲する社会技術的業務システムが、法令・権利・安全上の制約を維持しながら、変動や異常の下でも許容可能な成果と組織的accountabilityを保ち、必要に応じて安全に拒否・停止・縮退・復旧し、実際の仕事から適応能力を高める能力です。

## What can and cannot be delegated

AIへ委譲できるものは、主にtask、限定されたauthority、decision preparation、execution capabilityです。

次はAIへ移転したことにはなりません。

- 導入と運用を決定した組織のaccountability
- 法的liability
- 許容不能な危害を定める責任
- 影響を受けた人への説明と救済

最寄りのhuman operatorへ全責任を集中させてはいけません。情報、時間、技能、権限、実行手段を持たない承認者は、実質的な統制者ではありません。

## Constitutional constraints precede mission

目的を維持すること自体は善ではありません。違法・差別的・危険な目的も効率的に遂行できるためです。

優先順位は次の順序とします。

1. 法令、基本権、安全に関する非交渉制約
2. 顧客、労働者、取引先、第三者への許容不能な危害
3. その内側でのmissionとimpact tolerance
4. 業務効率、速度、利用率

安全・権利・不可逆な危害を、消費可能なerror budgetとして扱いません。

## Recovery includes refusal and cessation

レジリエンスは常時稼働を意味しません。状況によっては、次が正しい成果です。

- 操作を拒否する。
- read-onlyへ縮退する。
- 新規commitを停止する。
- 影響範囲を限定する。
- 人間へ返却する。
- 目標を放棄し、安全状態へ移る。

したがって「活動を継続できた割合」だけでは評価しません。

## Human adaptive capacity

人間を緊急停止ボタンや冗長部品として扱いません。human takeover readinessには、少なくとも次が必要です。

- competence
- situation awareness
- 判断に必要なinformation
- 現実に検討可能なtime
- 許容可能なworkload
- refusal、override、haltを行うauthority
- 停止後に安全状態へ移すactionability
- critical taskのpractice
- 異議を述べられるpsychological safety
- staffing coverage

個人のskill scoreを作るのではなく、定義したcritical taskについてteam capabilityを演習します。結果は非懲罰的なsystem learningに使用します。

## Work as imagined and work as done

- Contract、policy、runbookはWork-as-Imaginedです。
- Ledger、trace、Git、ticketはWork-as-Recordedです。
- 人間やagentによる説明はWork-as-Reportedです。
- Work-as-Doneは、それらと現場観察を突き合わせた推定です。

台帳だけからWork-as-Doneを完全に復元できるとは主張しません。

現場適応は常に良いものでも悪いものでもありません。有効な適応、危険な近道、risk transfer、逸脱の常態化を区別し、adaptive envelopeの中で検討します。

## Evidence and uncertainty

証拠は真実そのものではありません。

- hash chainは改ざん検知を支援しますが、sourceが正しいことは保証しません。
- traceはsamplingや配送欠損を含み得ます。
- external receiptも、外部systemの意味と結果を完全には保証しません。
- exerciseは特定条件下の実績であり、未知の事象への普遍的保証ではありません。

したがって、すべてのassurance claimにはscope、time、evidence source、freshness、independence、unknown、residual uncertaintyを伴わせます。

## Commitment

このプロジェクトは、次を約束します。

- 機械で検証できないものを、検証済みと表示しない。
- 安全停止と人間の異議申立てを失敗として扱わない。
- failureだけでなく、near missとeveryday successから学ぶ。
- 単一のresilience scoreへ潰さない。
- lock-inを回復能力の前提にしない。
- 自分自身の障害と誤判定をexercise対象にする。
- 標準、認証、法的適合を過剰に主張しない。
