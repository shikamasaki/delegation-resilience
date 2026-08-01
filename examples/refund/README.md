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

modelまたはpolicy serviceが停止した場合、read-only調査は継続できますが、新規返金commitを停止します。15分以内にhuman queueへ切り替え、結果不明の返金を再実行する前にprovider側の状態を照合します。

## Initial exercises

1. 返金成功後、agentがresponseを受け取る前にworkerが停止する。
2. 承認後、commit前にdelegationが取り消される。
3. fallbackへ切り替えたが、結果照会権限が不足している。
4. human approverが不在でhandover SLAを超過する。
5. evidence sinkが停止する。
6. primaryとfallbackが同じIdP停止の影響を受ける。

## Expected observations

- 二重返金が発生しない。
- response lossは`OUTCOME_UNKNOWN`になる。
- external reconciliation前にautomatic retryしない。
- stale grantではcommitできない。
- read、propose、commitが別々に縮退する。
- human takeoverの時間、情報、権限不足を記録する。
- exercise結果にscope、system version、残存不確実性を付ける。
