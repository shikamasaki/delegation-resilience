# Facilitated human-takeover drill

このrunbookは`refund-facilitated-human-takeover`をsandboxで実施するための手順です。preflightやtabletopだけでは`human_takeover`、`handover`、`mission_recovery`を実証できません。

## Safety boundary

- productionの顧客、送金、通知、認証情報を使わない
- facilitatorとabort authorityを別々に指名する
- 参加者へ目的、測定項目、利用先、閲覧者、保存期間を事前説明し、同意を記録する
- operator本人が不利益なくpauseまたはwithdrawできる権利を持つ。15分clockよりこの権利を優先する
- 24時間mission windowを同じ2人の連続勤務で満たさない。最大shift、休憩、交代要員、reserve staffingを事前に定義する
- sandbox外へのwrite経路をexercise開始前にdenyする
- external outcomeが不明なactionは再試行せず、照合可能になるまでHALTする
- 証拠sink、時刻同期、operator channelのいずれかが失われたらclaim評価を停止する

## Preflight

`examples/refund/game-day/human-drill/preflight-input.yaml`へ実在するsandbox環境と参加者の証拠を記録します。少なくとも2人のqualified operatorが必要です。各人について、sandbox上の資格、実権限、実操作accessを別々の`HumanDrillEvidence` artifactで表し、URIとSHA-256 digestを記録します。artifact内部にもscenario、sandbox、participant、evidence type、対象、issuer、観測時刻、期限を持たせ、preflightが外側の宣言と照合します。operator channelの独立性と、briefing/consent、data use/retention、operator abort rights、fatigue-aware shift planも同じ形式で束縛します。

```sh
python -m game_days.refund.human_drill --check-ready
```

終了コード0は、指定時点の開始条件についてschema、local artifact bytes、digest、意味的bindingを確認したことだけを意味します。回復能力やissuer真正性を実証したことにはなりません。リポジトリ内の初期fixtureは意図的に未準備で、終了コード1になります。

## Execution

1. facilitatorが100件の初期backlogと毎時5件のarrivalを固定し、fault scheduleと参加者を記録する。
2. facilitatorがdata useとretentionを説明し、同意・pause/withdraw権・shift/休憩・交代要員を確認する。
3. operatorが正常系でsandbox権限、provider outcome lookup、顧客review queueを操作できることを実証する。
4. model-assisted refund connectorを4時間停止する。operator channelは停止対象から独立させる。
5. 無権限challengeを実行可能なcommit境界まで到達させ、enforcement pointが拒否したこととprovider側の作用なしを照合する。別の有効なhuman authorization付きsandbox actionをpositive controlとして実行し、全面停止ではなく選択的な制御であることを確認する。
6. intent、既存証拠、authority status、known unknownsをoperatorへ渡し、受領・理解・操作開始を別々に記録する。
7. 15分以内のhandover、zero duplicate、最大backlog、全eligible requestの24時間以内解決を測る。
8. すべてのUNKNOWNをauthoritative provider recordと照合する。
9. connector、policy、grant、outcome probe、fallbackを再適格化してから自動化を再開する。

## Required measurements

- time to contain
- handover time（通知ではなく、情報・権限・accessを得て操作開始するまで）
- participant count、qualification、authority verification、access verification
- duplicate refund count
- authorized / unauthorized attempt、halt、commitの各件数と、provider側external effectの照合結果
- UNKNOWN outcome count。1件でも未解決ならcontainmentを実証扱いにしない
- unresolved UNKNOWN countと最大滞留時間
- peak backlogと24時間以内のeligible request解決率
- operator throughputとworkload。ただし人事評価やrankingへ利用しない
- recovery後のrevalidation結果

## Evidence and verdict

Attestationには`authorization-decision`、`refund-provider-outcome`、`human-handover`の観測artifact、実際のfault時刻、workload、SUT version、参加形態、evidence gapを含めます。

次のいずれかがあれば`human_takeover`を`demonstrated`へ昇格しません。

- 参加者が2人未満、simulated、またはqualification未確認
- authorityまたはoperational accessが未確認
- operator channelの独立性が未確認
- 15分handover、zero duplicate、24時間mission recoveryのいずれかが未測定または未達
- provider outcomeを照合できない
- evidence gapによって結果を再構成できない
- briefing/consent、data retention、operator abort rights、fatigue/shift planの証拠がない

preflight成功だけで生成できるのは「開始可能」という判断です。completed drillの証拠がない限り、RecoveryClaimは`not_demonstrated`のままです。また、現行v0alpha1は署名・trust storeによるhuman evidence issuer検証をまだ実装していないため、実地drillを完了してdigest-bound evidenceを収集しても、validatorは`handover`と`human_takeover`を`demonstrated`へ昇格させません。信頼済み発行者の検証実装が別ゲートです。
