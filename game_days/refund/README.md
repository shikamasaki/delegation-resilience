# Refund response-loss Game Day

最初の実行可能なRecovery Game Dayです。返金providerがcommitした直後にresponseを失う同一fault scheduleを、二つのworkflowへ適用します。

## Compared contracts

`profile_aware`:

- logical intent IDをnative idempotency keyとして固定する。
- timeoutをepistemic `UNKNOWN`として記録する。
- retry前にauthoritative provider lookupで外部結果を照合する。

`conventional_retry` baseline:

- timeoutを`FAILED`として扱う。
- execution attemptごとに新しいidempotency keyを生成する。
- 最初のattemptを外部照合せずretryする。

BaselineはTransactional Action Profileへ適合しない意図的な比較対象であり、すべての一般的なretry実装を代表しません。比較対象のcontractを成果物へ明示し、この前提を超えて結果を一般化しません。

> Scope: The baseline represents attempt-scoped idempotency with retry-before-reconciliation. It does not represent every conventional retry implementation.

## Fixed conditions

- initial backlog: 100 requests
- arrivals: 5 requests/hour
- simulated duration: 1 hour
- total intents: 105
- response-loss-after-commit: 10 intents
- seed: `refund-response-loss-v0alpha1-seed-1`
- human participants: 0

Fault対象は、seedとintent IDのSHA-256順位で選ぶため、Pythonのrandom実装へ依存しません。

## Run

```bash
python3 -m pip install -r requirements-validation.txt
python3 -m game_days.refund.runner --write
python3 -m game_days.refund.runner --verify
```

生成物は[examples/refund/game-day](../../examples/refund/game-day/)へ保存します。

- `run-report.json`: 条件、variant別結果、material gap
- `evidence/profile-aware-provider-outcomes.json`: profile-aware側のeventとauthoritative effect
- `evidence/baseline-provider-outcomes.json`: retry baseline側のeventとauthoritative effect
- `attestation.yaml`: profile digestとevidence digestを持つsynthetic Attestation

Profile digestはRFC 8785 JCSのcanonical bytesへSHA-256を適用します。Evidence digestは保存されたartifact bytesそのものへSHA-256を適用します。

## Expected result

| Measurement | profile-aware | conventional retry |
|---|---:|---:|
| effects whose commit response was lost | 10 | 10 |
| effects unrecognized at workflow completion | 0 | 10 |
| UNKNOWN resolved by reconciliation | 10 | 0 |
| external effects | 105 | 115 |
| duplicate refunds | 0 | 10 |

両variantが同じ10件の通信障害を受けています。違いは障害の回避ではなく、profile-aware側が外部照合によって事実を回復し、安全に収束したことです。Baselineではambiguous commitを`FAILED`へ潰すこととattempt-scoped idempotencyの組合せにより、workflow終了時にも認識されない外部effectが残ります。

この結果は「Delegation Resilience全体が実証された」ことを意味しません。

## Assurance boundary

Attestationは`not_demonstrated`を維持し、`external_reconciliation`だけを部分的なdemonstrated capabilityとして記録します。

未実証のまま残るもの：

- human takeover
- 15分handover
- 24時間mission recovery
- production providerとの同等性
- policy、IdP、evidence sinkを含むshared-fate
- operator capacity
