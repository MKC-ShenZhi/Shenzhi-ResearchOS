# Venue rankings（CS/AI 常用，按声誉粗分）

分层依据是社区共识的粗档，不是精确排名；知识库语料以 CS/AI 为主，其他学科凭 venue 常识判断。

## 顶会/顶刊档

- AI/ML：NeurIPS、ICML、ICLR
- CV：CVPR、ICCV、ECCV
- NLP：ACL、EMNLP、NAACL
- 数据挖掘/检索：SIGIR、KDD、WWW
- 系统：OSDI、SOSP、NSDI
- 期刊：TPAMI、JMLR、Nature 系、Science

## 强会档

AAAI、IJCAI、COLING、CIKM、WSDM、AISTATS、UAI、INTERSPEECH、ACM MM

## 使用规则

- 分层判据里的"venue 权威"以此表为参考；表外的 venue 凭名称与领域常识判断，不确定时不加分。
- 预印本（arXiv 等）无 venue 声誉加成，但新近性可以补偿——活跃方向的前沿工作常以预印本形式存在，不要仅因预印本而降层；若 `citation_graph` 确实返回 CITES 边，可据此追踪后续工作，否则通过 `paper_search` 另行核对。
- venue 声誉是分层的一个输入，不是决定因素：直接相关性永远第一位。
