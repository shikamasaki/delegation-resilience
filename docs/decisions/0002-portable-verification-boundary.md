# ADR-0002: Use a portable verification boundary

## Status

Accepted for v0alpha2.

## Decision

Exercise artifactへ独自の署名fieldを埋め込みません。Bundle全体はin-toto StatementをDSSE署名し、artifact sourceごとのproofもdetached DSSEとして保持します。AlgorithmはEd25519に固定し、trust policyはconsumerがbundle外から指定します。

Semantic validation、artifact integrity、signature validity、issuer trust、dependency freshness、claim support、deployment decisionを別軸にします。Standalone verifierはrunner/generatorを含まず、content-addressed code manifestとcanonical `VerificationResult`を出力します。

Human evidenceの署名検証を実装しても、それだけでhuman capability ceilingを解除しません。

## Reasons

- detached proofはartifactの自己参照digestを避ける
- DSSE PAEはpayload type confusionを避ける
- in-toto subjectはpacket内raw bytesを既存形式で束縛する
- bundle内の配置ごとにartifact roleを固定し、opaque subjectも実在性とdigestを検査する
- external trust policyはbundle同梱keyによるself-trustを避ける
- runnerとverifierの分離は同じ欠陥の共有を減らす
- version labelではなくverifier code digestを再現条件にする
- key失効とdependency変更を分離するとremediationが明確になる

## Consequences

- 同じartifactでもtrust policy、評価時点、dependency snapshotが違えば正当に異なる結果になる
- signatureはtruth、completeness、independent assessmentを証明しない
- trusted timestampがないためrevoked keyのhistorical signatureもrejectする
- v0alpha2はdirectory bundleとsource-distributed verifierであり、global PKIやmanaged transparency serviceではない
