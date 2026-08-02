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

各runには再利用しない`preflightRunId`と予測困難な一回限りの`challenge`を発行します。briefing本文を`briefingArtifact`としてdigest固定し、利用目的・閲覧者・保存期限を`participantDataUse`へ記録します。facilitatorとabort authorityは別identityとし、それぞれのassignmentを外部issuerが署名します。participantのacknowledgementと直前statusは、run ID、challenge、profile digest、preflight context digest、briefing digest、単調増加`statementSequence`へ本人署名で束縛します。

```sh
python -m game_days.refund.human_drill --check-ready \
  --trust-policy /independent/path/trust-policy.yaml \
  --min-policy-sequence 42 \
  --participant-sequence-highwatermarks /consumer/state/participant-sequence-highwatermarks.yaml
```

`--trust-policy`を指定した場合、preflightは各human evidence artifactのDSSE proof、payload type、Ed25519 key、issuer authorization、subject/object/covers scope、失効、independence domainも検証します。Trust policyはbundle外から渡し、同梱keyをtrust rootへ昇格しません。既知のpolicy high-watermarkを`--min-policy-sequence`で必ず指定します。同じissuer identityを複数domainとして数えません。

`--participant-sequence-highwatermarks`は、検証対象manifestとは別にconsumerが保持する最新観測statementです。trust policy ID/sequence、run ID、challenge、全participantに加え、各participantのsequence、status、statement digestを正確に束縛します。consumerは受理した最新statementを原子的に保存します。一度`withdrawn`を観測したrunではwithdrawalをstickyに扱い、より新しい`active`も受理しません。古いsequenceだけでなく、同一sequenceでbytesまたはstatusが異なるequivocationも拒否します。このファイルはglobalな「現在」を自動発見する仕組みではありません。実行責任者はparticipantのwithdrawal経路から更新し、fault注入の直前にpreflightを再実行します。更新経路が利用不能、競合、または不明なら開始しません。

Qualification、authority、access、channel independence、safeguard、facilitator/abort-authority assignment evidenceはparticipant本人、facilitator、abort authorityから分離したissuerが署名します。Participant acknowledgementとwithdrawal statusだけは当該participant本人が署名し、それぞれ`acknowledged / declined`、`active / withdrawn`を明示します。Declineまたはwithdrawalはpreflightを停止し、本人署名を独立observer domainの代用にはしません。

終了コード0は、指定時点の開始条件についてschema、local artifact bytes、digest、意味的binding、指定trust policy下のissuer authorizationを確認したことだけを意味します。回復能力やexercise完了を実証したことにはなりません。リポジトリ内の初期fixtureは意図的に未準備で、終了コード1になります。

## Execution

1. facilitatorが100件の初期backlogと毎時5件のarrivalを固定し、fault scheduleと参加者を記録する。
2. facilitatorがdigest固定済みbriefingに沿ってdata useとretentionを説明し、同意・pause/withdraw権・shift/休憩・交代要員を確認する。各participantが自分のacknowledgementを署名する。
3. operatorが正常系でsandbox権限、provider outcome lookup、顧客review queueを操作できることを実証する。
4. participant statusとconsumer-held sequence high-watermarkを更新し、同じrun/challengeでpreflightを再実行する。全員activeかつreadyでなければ中止する。
5. model-assisted refund connectorを4時間停止する。operator channelは停止対象から独立させる。
6. 無権限challengeを実行可能なcommit境界まで到達させ、enforcement pointが拒否したこととprovider側の作用なしを照合する。別の有効なhuman authorization付きsandbox actionをpositive controlとして実行し、全面停止ではなく選択的な制御であることを確認する。
7. intent、既存証拠、authority status、known unknownsをoperatorへ渡し、受領・理解・操作開始を別々に記録する。
8. 15分以内のhandover、zero duplicate、最大backlog、全eligible requestの24時間以内解決を測る。
9. すべてのUNKNOWNをauthoritative provider recordと照合する。
10. connector、policy、grant、outcome probe、fallbackを再適格化してから自動化を再開する。

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

preflight成功だけで生成できるのは「開始可能」という判断です。completed drillの証拠がない限り、RecoveryClaimは`not_demonstrated`のままです。v0alpha2で署名、issuer authorization、preflight/run ID、challenge、participant acknowledgement/withdrawalの直前性までは検証できますが、observer、handover observation、human task outcome、external reconciliation、職務分離が一つのcompleted runへ束縛されるまでは、validatorは`handover`と`human_takeover`を`demonstrated`へ昇格させません。
