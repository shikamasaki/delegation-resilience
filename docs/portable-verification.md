# Portable Verification v0alpha2

## Outcome

v0alpha2が提供するのは独立認証ではなくportable verificationです。ここでいう同じpacketとは、DSSE envelopeだけでなく、そのsigned subject inventoryが列挙する全raw artifact bytesを含みます。同じpacket、verifier code digest、environment digest、評価時点、外部trust policy、consumer high-watermarkを使った場合、同じ限定的な`VerificationResult`をofflineで再現できます。Version文字列だけは実装同一性の根拠にしません。

`packetVerificationOutcome: PACKET_VERIFIED`とCLI終了コード0が意味するのは、packetの構造、integrity、signature/trust処理が完了したことだけです。Claimが`SUPPORTED`、freshnessがcurrent、deploymentが許可可能、安全、適合、認証済みであることを意味しません。CI/CDで利用するconsumerは、別の明示的policyで`checks.freshness`、各`claimResults`、残存gap、deployment decisionを評価します。

```text
DSSE envelope
└─ in-toto Statement
   ├─ signed subject inventory (raw-byte SHA-256)
   └─ VerificationBundle predicate
      ├─ profile
      ├─ ExerciseAttestation + source proof
      ├─ evidence + source proof
      ├─ opaque SUT artifacts
      └─ DependencySnapshot + source proof

consumer-supplied TrustPolicy
          ↓
runner-free standalone verifier
          ↓
canonical VerificationResult
```

## What is verified

- strict JSON/YAML loading、duplicate keyとnon-JSON valueの拒否
- local path containment、symlink/path traversal拒否、raw-byte digest
- in-toto subjectの全artifact実在性、digest、case collision、配置ごとのrole
- DSSE PAEとEd25519 signature
- public-key digestから導出した`keyid`
- bundle外trust policyによるissuer、purpose、artifact kind、scenario、environment scope
- policy/key validity、key revocation、statement revocation、minimum policy sequence
- profile、Attestation、evidence、dependency snapshotのSchemaとcross-artifact semantics
- `any_change → STALE`、`manual_review → REVIEW_REQUIRED`
- Refund profileのworkload、seed、fault countから独立再構成したprofile-aware variantの完全なdeterministic witnessとの一致
- verifier source、Schemaのcode digestと、interpreter binary、platform ABI、declared verifier distributionsの全installed file bytesを含むenvironment digest

Verifierはexercise generatorをimportまたは実行しません。Refund checkerはprofileの固定条件からprofile-aware variantの全intent、faulted intent、event、external effect、summaryを別実装で再構成し、signed evidenceとの完全一致を要求します。Baseline artifactは署名と構造を検査しますが、portable capabilityの根拠には使いません。未対応scenarioはportable capabilityを返さず、replayも無効化しません。

## What is not verified

- evidence sourceが真実または完全であること
- caller提供のdependency snapshotがrunning deploymentの現状を真実に表すこと
- exerciseが本番条件を完全に再現したこと
- humanの一般的な技能や実運用能力
- system全体の安全、法令適合、認証
- deploymentが許容可能であること

署名はbytesをauthorized keyへ結びます。署名済み自己申告を、真実や第三者保証へ読み替えません。`VerificationResult.decisionBoundary.deploymentDisposition`は常に`NOT_EVALUATED`です。

## Trust and revocation

Trust policyはbundle外から明示的に指定します。Bundle内のkeyやself-claimed issuerをtrust anchorにしません。v0alpha2はEd25519だけを許可し、`keyid`はraw public key bytesのSHA-256です。

Trusted timestampやtransparency logは未実装です。したがってrevoked keyの署名は、artifactの自己申告時刻にかかわらず全期間rejectします。Trust policyには単調増加`sequenceNumber`があり、consumerは必須の`--min-policy-sequence`で既知のhigh-watermark未満を拒否します。指定したhigh-watermarkも`VerificationResult.inputs.minimumTrustPolicySequence`へ記録します。TUF、Sigstore keyless、Rekor、RFC 3161、OCSP、HSM/KMSは後続です。

Cryptographic trust revocationとassurance invalidationを混同しません。

- key/statement/policyの問題: signatureまたはissuer trust failure
- model/tool/policy/grant/connector等の変更: claim freshnessの`STALE / REVIEW_REQUIRED`

## Run

```bash
python -m pip install -r requirements-verifier.txt
verifier_code_digest=$(python -c 'from tools.verifier_manifest import verifier_code_digest; print(verifier_code_digest())')
verifier_environment_digest=$(python -c 'from tools.verifier_manifest import verifier_environment_digest; print(verifier_environment_digest())')
python tools/verify_bundle.py \
  examples/refund/portable-verification/bundle.dsse.json \
  --trust-policy examples/refund/portable-verification/trust-policy.json \
  --artifact-root examples/refund/portable-verification \
  --as-of 2026-08-03T00:00:00Z \
  --min-policy-sequence 1 \
  --expected-verifier-code-digest "$verifier_code_digest" \
  --expected-verifier-environment-digest "$verifier_environment_digest"
```

Runnerを含まない配布物は空directoryへexportできます。

```bash
python tools/export_verifier.py /tmp/delegation-resilience-verifier
python /tmp/delegation-resilience-verifier/tools/verify_bundle.py ...
```

Exportには`VERIFIER-MANIFEST.json`が含まれ、公開用`codeDigest`と`environmentDigest`も記録されます。consumerは配布経路など別の信頼経路で取得した両digestを必須CLI引数として固定します。検証器が自分で測った値をそのまま期待値にすると、実体の独立固定にはなりません。`VerificationResult.verifier.codeDigest`はsourceとSchemaのfile inventoryを、`environmentDigest`はCPython interpreter binary、patch version、platform/ABI、およびdeclared verifier distributionsの全installed file bytesを別々に束縛します。Reference runtimeはCPython 3.12.8です。

`environmentDigest`は同じpacketの判定を同じ実行環境で再現するための変更検出です。OS全体、preloaded module、`sitecustomize`、process injectionまで無欠性を証明するhermetic runtime attestationではありません。その保証が必要なconsumerは、別の信頼経路で固定したcontainer/VM imageとprocess isolationを併用します。このため、repositoryのreference `verification-result.json`と異なるplatformのCI出力はbyte比較せず、CI内の同一環境で2回の結果が一致することを検証します。

Reference bundleのprivate key seedはtest fixtureとして公開されています。暗号経路と再現性のデモだけを目的とし、実在issuerへのtrustを表しません。

## Human drill boundary

Human preflightはtrusted DSSE evidenceを受理します。Qualification、authority、access、channel independence、safeguard、facilitator/abort-authority assignmentはparticipant本人、facilitator、abort authorityによる自己証明を拒否します。一方、acknowledgementとwithdrawal statusは当該participant本人だけが署名でき、`declined`と`withdrawn`を表現でき、独立検証domain数には算入しません。本人statementは一回限りのrun/challenge、profile、preflight context、briefing artifact、単調増加sequenceへ束縛されます。consumer-held stateはsequenceだけでなくstatusとstatement digestを保持します。古いactive、同一sequenceの異なるbytes/status、または一度観測済みのwithdrawal後のactiveはすべて拒否します。Scope外issuer、payload type confusion、失効、policy rollback、同一issuerによる複数independence domainも拒否します。ただし開始可能性とcapability demonstrationは別です。Completed drillのobserver、handover/task outcome、external reconciliationが同じrunへ機械可読に結ばれるまでは、`handover`と`human_takeover`を昇格させません。
