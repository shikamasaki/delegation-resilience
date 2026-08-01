# Transactional Action State Model

## Purpose

外部状態を変更するworkflowでは、logical intent、複数のexecution attempt、外部効果についての知識、実際の外部状態、reconciliation、compensationを一つのenumへ混在させません。

状態語彙と一時点のsnapshot構造は[JSON Schema](../profiles/transactional-action/schema/runtime-state.schema.json)でも定義します。Schemaは値と構造を検証し、許可遷移とinvariantは本書および将来のconformance linterが検証します。

## 1. Logical intent lifecycle

```text
REGISTERED → PREPARED → AUTHORIZED → COMMIT_REQUESTED → CLOSED_NO_EFFECT
     │           │          │                 └──────→ CLOSED_WITH_EFFECT
     └───────────┴──────────┴→ CANCELLED_PRE_COMMIT
```

- `REGISTERED`: stable intent IDとcanonical payloadを記録済み
- `PREPARED`: precondition evidenceとimpact reservationを評価済み
- `AUTHORIZED`: grant、policy digest、expiryへ束縛されたauthorityが有効
- `COMMIT_REQUESTED`: 少なくとも一つのexecution attemptを開始した
- `CLOSED_NO_EFFECT`: commit attempt開始後、外部効果がなかったことをauthoritative sourceで確認した
- `CLOSED_WITH_EFFECT`: 外部効果を照合し、必要なrecoveryまたはcompensation episodeを完了した
- `CANCELLED_PRE_COMMIT`: execution attempt開始前に取消した

execution attempt開始後は`CANCELLED_PRE_COMMIT`へ移行できません。外部効果がなかった場合も、照合後に`CLOSED_NO_EFFECT`へ移行します。

## 2. Execution attempt

一つのintentは複数attemptを持ち得ます。

```text
STARTED → ACKNOWLEDGED
       ├→ TIMED_OUT
       └→ ABORTED
```

- `ACKNOWLEDGED`はconnectorが応答を得たことを表し、外部成果の正しさを保証しない。
- `TIMED_OUT`は外部failureを意味しない。
- retryは新しいattempt IDを作り、同じintent IDとidempotency keyへ関連付ける。

## 3. Epistemic outcome

```text
UNKNOWN
├→ CONFIRMED_SUCCEEDED
├→ CONFIRMED_FAILED
└→ PARTIAL
```

Epistemic outcomeは「現在何を知っているか」です。外部効果そのものではありません。

- timeout、response loss、観測source停止は原則`UNKNOWN`
- `UNKNOWN`ではblind retryしない
- conflicting evidenceがある場合はconfirmationへ進めない

## 4. External effect

```text
NONE
APPLIED
PARTIALLY_APPLIED
REVERSED
```

- `REVERSED`: authoritative systemが元の意味的状態へ戻ったことを確認済み
- irreversibilityはeffect stateではなくTransactionalActionProfile上のproperty

外部effectは可能な限りauthoritative outcome probeから導出します。

## 5. Reconciliation

```text
NOT_REQUIRED
PENDING → MATCHED | MISMATCHED | SOURCE_UNAVAILABLE
```

- `MATCHED`: ledger上のclaimとauthoritative external stateが一致
- `MISMATCHED`: 二重実行、欠落、部分成功などの差がある
- `SOURCE_UNAVAILABLE`: 照合sourceへ到達できない

`MISMATCHED`と`SOURCE_UNAVAILABLE`をsuccessとしてcloseしません。

## 6. Compensation episode

```text
NOT_REQUIRED
AVAILABLE → REQUESTED → SUCCEEDED | FAILED
UNAVAILABLE
IMPOSSIBLE
```

Compensationは独立したlogical intent、authority、evidence、external effectを持ちます。元actionのstateを上書きしません。

例えば元actionが実行され、その後に補償actionが成功した場合は、元actionについて`externalEffect = APPLIED`と`compensationState = SUCCEEDED`を同時に保持し、`compensationIntentRef`で別intentを参照します。

## Safety invariants

1. 同じintentとidempotency domainで、同時に複数の有効commit authorityを発行しない。
2. Epistemic `UNKNOWN`の間、impact reservationを解放しない。
3. Native idempotencyまたはequivalent fencingがない不可逆actionを自動retryしない。
4. Grant revocation、policy generation変更、expiryをcommit pointで再確認する。
5. Reconciliation未完了のintentを通常状態への復帰条件に使わない。
6. Compensation成功を元actionの未実行として記録しない。

## Crash and concurrency requirements

- durable pre-commit recordが書けなければ外部commitしない。
- worker再起動後はpending attemptを外部照合してから再実行判断を行う。
- fallback workerは新epochを取得し、旧workerをfenceする。
- 外部systemがfencing tokenを検証できない場合、その限界をclaimへ明示する。
- wall-clock timestampだけでeventの全順序を仮定しない。

## Initial conformance scenarios

- external success followed by response loss
- duplicate delivery of the same intent
- revocation between authorization and commit
- concurrent primary and fallback workers
- authoritative outcome source unavailable
- partial external effect followed by compensation failure
