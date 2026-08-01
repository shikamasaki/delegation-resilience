# Landscape and References

Research date: 2026-08-02

この文書は完全な市場一覧ではありません。Delegation Resilienceの知的系譜、隣接領域、重複を継続的に確認するためのstarting pointです。

## Intellectual foundations

- [Resilience Engineering Association](https://www.resilience-engineering-association.org/about-rea/): Respond、Monitor、Learn、Anticipateと、日常業務における適応。
- [REA — Learning from Everyday Work](https://www.resilience-engineering-association.org/blog/2020/04/05/learning-from-everyday-work/): failureだけでなくeveryday workから学ぶ考え方。
- [Bank of England SS1/21](https://www.bankofengland.co.uk/prudential-regulation/publication/2021/march/operational-resilience-impact-tolerances-for-important-business-services-ss): important business service、impact tolerance、dependency mapping、severe-but-plausible testing。
- [NIST SP 800-160 Vol. 2 Rev. 1](https://csrc.nist.gov/pubs/sp/800/160/v2/r1/final): anticipate、withstand、recover、adaptを含むcyber resilience engineering。
- [Bainbridge — Ironies of Automation](https://www.sciencedirect.com/science/article/pii/0005109883900468): 自動化と人間の技能・異常時対応の緊張関係。
- [Elish — Moral Crumple Zones](https://doi.org/10.17351/ESTS2019.260): 自動化systemの失敗時に最寄りのhuman operatorへ責任が集中する問題。

## AI governance and emerging standards

- [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework): voluntaryなAI risk management framework。
- [NIST AI 600-1](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf): third-party contingency、fallback/manual processing、定期演習、retrospective、chaos testing、affected communityとのengagementを含むGenerative AI Profile。
- [NIST AI Agent Standards Initiative](https://www.nist.gov/artificial-intelligence/ai-agent-standards-initiative): agent identity、authorization、security、interoperabilityに関する2026年のinitiative。
- [AWS Agentic AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentops01.html): business outcome、autonomy boundary、human handoff、failure testing、behavioral change後の再検証、continuous improvementを含むoperational guidance。
- [ISO/IEC/IEEE 15026-2:2022](https://www.iso.org/standard/80625.html): assurance caseのminimum requirements。Assurance case自体を新しい概念として主張しない。
- [ISO/IEC AWI TS 25864](https://www.iso.org/standard/91831.html): AI system resilience assessment。2026-08-01時点でStage 20.00。
- [EU AI Act Article 14](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng): high-risk AIにおけるhuman oversight、override、stop、competence、authority。
- [Singapore IMDA Model AI Governance Framework for Agentic AI](https://www.imda.gov.sg/resources/press-releases-factsheets-and-speeches/press-releases/2026/new-model-ai-governance-framework-for-agentic-ai): agentic AIのgovernance framework。
- [日本政府 生成AI調達・利活用ガイドライン第2.0版](https://www.digital.go.jp/news/decb64eb-f26e-41cb-8d37-f3dd173108b8): 政府調達・利用におけるAI agent、権限、log、model update、risk対応。

## Technical building blocks

- [Open Policy Agent](https://www.openpolicyagent.org/): policy decisionとlocal evaluation。Delegation Resilienceは独自policy engineを再実装しない。
- [Cedar](https://www.cedarpolicy.com/): analyzableなauthorization policy。
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/): telemetry correlation。監査上のauthoritative evidence storeとは区別する。
- [W3C PROV](https://www.w3.org/TR/prov-primer/): provenance interchangeの基礎model。
- [Temporal](https://docs.temporal.io/): durable execution。外部副作用の真実、目的の正しさ、idempotencyを自動的には保証しない。
- [MCP Authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization): tool accessのauthorization boundary。
- [A2A](https://github.com/a2aproject/A2A): agent間のdiscoveryとtask transport。capability declarationをdelegated authorityの証明とはみなさない。

## Adjacent products and specifications

次は重要な隣接領域であり、空白ではありません。

- [ServiceNow AI Control Tower](https://www.servicenow.com/products/ai-control-tower.html): enterprise-wide inventory、governance、risk、observability、business service mapping。
- [Microsoft Entra Agent ID](https://learn.microsoft.com/en-us/entra/id-governance/identity-governance-overview): agent identity、human sponsor、lifecycle、access review、revocation。
- [AWS AgentCore Policy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-core-concepts.html): Cedarによるtool-call authorization。
- [Delegation Contract](https://www.delegationcontracts.org/): coding agentへのtask entry、authority、work package、human acceptanceを記述するworking specification。
- [Agent Definition Language](https://www.adl-spec.org/): identity、permission、lifecycle、complianceを記述するmachine-readable agent definition。
- [Agent Governance Protocol](https://www.agp-protocol.dev/docs): fail-closed execution、delegatable capability、audit trail。
- [Grantex](https://grantex.dev/): scoped、time-limited、revocableなagent authorization。

Delegation Resilienceの仮説上の差分は、inventoryやallow/denyそのものではなく、missionとimpact toleranceを起点に、external outcome reconciliation、safe degradation、human takeover、fallback qualification、recovery exercise、learning decisionを一つのassurance lifecycleへ結ぶことです。

この差分が顧客価値として確認できなければ、独立製品化しません。

## Claim-level boundary

| Capability | Existing guidance/products | Delegation Resilience focus |
|---|---|---|
| Business outcome and autonomy boundary | AWS Agentic AI Lens、NIST AI RMF | 独自性を主張しない。MissionSpecへ参照する |
| Authorization and identity | AWS AgentCore、Microsoft Entra、OPA/Cedar、delegation protocols | 再実装せず、DelegationGrantとenforcement evidenceへ接続する |
| Handoff and fallback | AWS Agentic AI Lens、NIST AI 600-1 | configuredではなく、claim別のqualificationとhuman takeover conditionを記録する |
| Failure exercise | AWS Lens、NIST AI 600-1、eval/chaos products | external effect、epistemic state、mission adequacyまで同じscenarioで照合する |
| Assurance case | ISO/IEC/IEEE 15026-2 | AI delegation境界へclaim、mechanism、attestation、uncertaintyを適用する |
| Resilience assessment | ISO/IEC TS 25864策定中 | 競合標準を先取りせず、実験結果とmappingを提供する |
| Human oversight | EU AI Act、human factors literature | information、time、competence、authority、actionabilityをexercise条件として残す |

新規性の主張は個々の部品ではなく、mission単位の限定claimに対して、外部結果のepistemic state、fallback/human takeoverのqualification、証拠mechanism、exercise result、残存不確実性をvendor-neutralなassurance lifecycleとして結ぶ統合単位に限定します。
