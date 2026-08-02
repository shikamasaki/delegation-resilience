# Refund workflow reference scenario

このscenarioは、非coding領域でreference modelを検証するための最小例です。実在企業のpolicyではなく、設計議論用の例です。

## Mission

顧客の正当な返金要求を、権利・財務・不正防止上の制約を守りながら24時間以内に解決します。

## Actions

- `read_order`: read-only
- `propose_refund`: 外部副作用なし
- `execute_refund`: 財務上の副作用あり。native idempotency keyと結果照会を必須とする
- `notify_customer`: 外部コミュニケーション。送信後は意味的に不可逆

## Delegation

- agentは注文を読み、返金を提案できる。
- 1万円以下は、必要証拠が揃い、異常がない場合に限り実行できる。
- 1万円を超える返金、送金先変更、bank account変更は人間判断を必要とする。
- agentは自身の権限拡張、approval、policy変更を行えない。

## Recovery claim

Recoveryを次の四段階で評価します。

- `contain`: modelまたはpolicy serviceが停止したら、新規返金commitを止め、boundedなread-only調査だけを継続する。
- `handover`: 15分以内に、intent、evidence、authority status、known unknownsを伴ってhuman queueへ引き継ぐ。
- `recover`: 正当な要求を24時間以内に解決し、backlogを許容範囲内に保ち、二重返金を発生させない。
- `revalidate`: unknown actionを外部照合し、policy、grant、connector、fallbackを再検証してから自動処理を再開する。

Queueへ移しただけではrecoveryとみなしません。[Machine-readable profile](profile.yaml)がこのclaimと初期exerciseを定義します。

この例ではbacklog上限100件、24時間のoperator coverage、毎時20件のmanual capacity、provider APIの4時間以内の復旧を明示的な仮定にしています。いずれも未実証なので、claimは`ASSERTED / PROHIBITED`です。仮定を隠して一般的なprovider outageへの回復を主張しません。

## Initial exercises

実証目的を混ぜず、次の四つへ分けます。

1. `Deterministic test`: response loss、idempotency、revocation、reconciliation、fencing。
2. `Shared-fate test`: IdP、policy、provider status API、operator channelの共通障害。
3. `Facilitated human drill`: 15分handover、必要情報、実権限、queue capacity、24時間mission recovery。
4. `Baseline comparison`: 通常retry実装との二重実行数、unknown滞留時間、回復時間、operator workload比較。

[Machine-readable profile](profile.yaml)では、各scenarioに初期backlog、毎時arrival、fault継続時間、operator数と能力、shared dependency、response-loss件数、固定random seedを宣言します。未宣言のloadへ結果を一般化しません。

最初のdeterministic comparisonは[Refund response-loss Game Day](../../game_days/refund/README.md)として実行できます。生成済みの[run report](game-day/run-report.json)と[synthetic Attestation](game-day/attestation.yaml)も同じ条件から再生成できます。

Shared-fate exerciseも同じprofileから実行でき、[run report](game-day/shared-fate/run-report.json)と[synthetic Attestation](game-day/shared-fate/attestation.yaml)を生成します。これは宣言された依存トポロジーのdeterministic simulationであり、実在するIdP、policy、provider API、operator channelを試験した証拠ではありません。

Facilitated drillは[runbook](../../game_days/refund/HUMAN_DRILL.md)と[fail-closed preflight](game-day/human-drill/preflight-report.json)で準備します。現在のfixtureは意図的に`ready: false`であり、実地演習済みとは扱いません。

[Portable verification bundle](portable-verification/bundle.dsse.json)は、response-loss exerciseのprofile、Attestation、evidence、SUT artifact、dependency snapshotをsigned in-toto manifestへ束縛します。Standalone verifierはprofile条件からdeterministic witnessを独立再構成します。[Canonical VerificationResult](portable-verification/verification-result.json)は、packet処理だけを`PACKET_VERIFIED`としつつ、claim全体を`UNKNOWN`、`external_reconciliation`だけをsupported capability、human takeoverをunsupportedとして再現します。reference鍵は公開されたtest-only鍵であり、実在組織へのtrustを意味しません。

## Expected observations

- 二重返金が発生しない。
- response lossはepistemic `UNKNOWN`になる。
- external reconciliation前にautomatic retryしない。
- stale grantではcommitできない。
- read、propose、commitが別々に縮退する。
- human takeoverの時間、情報、権限不足を記録する。
- exercise結果にscope、system version、残存不確実性を付ける。

## Comparative experiment

同じfault scheduleを、profile-aware workflowと通常のretry実装へ適用します。

- duplicate refunds
- epistemic `UNKNOWN`の滞留時間
- time to contain、handover、recover
- operator workload
- 既存log/evalでは分からなかったmaterial gap

を比較し、単にscenarioをpassしたかではなく、回復設計が実際に差を生むかを検証します。
