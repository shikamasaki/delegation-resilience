# Contributing

Delegation Resilienceはpre-specification段階です。現時点では、機能追加より問題定義と反証可能性を優先します。

## Valuable contributions

- 定義に対する反例
- 実際のfailure、near miss、everyday success
- 文書上のfallbackが機能しなかった事例
- human oversightが形骸化した条件
- 測定不能またはgaming可能なmetricの指摘
- 既存標準、OSS、商用製品との重複
- 異なる業務領域で再利用できなかった概念
- privacy、labor、rights、safety上の懸念

## Proposal process

1. Issueでproblem、affected stakeholders、existing alternativesを説明する。
2. 変更が解くclaimと、解かないclaimを明示する。
3. `ENFORCEABLE / OBSERVABLE / EXERCISABLE / ASSERTED / UNSUPPORTED`のどこに属するか示す。
4. 代表scenarioとcounterexampleを用意する。
5. 意味変更はADRまたはversioned proposalとしてreviewする。

## Standards language

本projectは現時点で国際標準や認証schemeではありません。複数の独立実装と中立的governanceが成立するまでは、contribution内でも`standard`、`certified`、`compliant`という表現を根拠なく使用しないでください。

## Code of conduct

人間の失敗、現場適応、drill結果を個人非難へ利用しません。異なる職種、影響を受ける当事者、frontline workerの知識を尊重し、system-levelの学習を優先してください。
