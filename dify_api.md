

POST/datasets/{dataset\_id}/document/create-by-text

通过文本创建文档
--------

此接口基于已存在知识库，在此知识库的基础上通过文本创建新的文档

### Path

*   `dataset_id`
    
    string
    
    知识库 ID
    

### Request Body

*   `name`
    
    string
    
    文档名称
    
*   `text`
    
    string
    
    文档内容
    
*   `indexing_technique`
    
    string
    
    索引方式
    
    *   `high_quality` 高质量：使用  
        ding 模型进行嵌入，构建为向量数据库索引
    *   `economy` 经济：使用 keyword table index 的倒排索引进行构建
    
*   `doc_form`
    
    string
    
    索引内容的形式
    
    *   `text_model` text 文档直接 embedding，经济模式默认为该模式
    *   `hierarchical_model` parent-child 模式
    *   `qa_model` Q&A 模式：为分片文档生成 Q&A 对，然后对问题进行 embedding
    
*   `doc_language`
    
    string
    
    在 Q&A 模式下，指定文档的语言，例如：`English`、`Chinese`
    
*   `process_rule`
    
    object
    
    处理规则
    
    *   `mode` (string) 清洗、分段模式 ，automatic 自动 / custom 自定义
    *   `rules` (object) 自定义规则（自动模式下，该字段为空）
        *   `pre_processing_rules` (array\[object\]) 预处理规则
            *   `id` (string) 预处理规则的唯一标识符
                *   枚举：
                    *   `remove_extra_spaces` 替换连续空格、换行符、制表符
                    *   `remove_urls_emails` 删除 URL、电子邮件地址
            *   `enabled` (bool) 是否选中该规则，不传入文档 ID 时代表默认值
        *   `segmentation` (object) 分段规则
            *   `separator` 自定义分段标识符，目前仅允许设置一个分隔符。默认为 `\n`
            *   `max_tokens` 最大长度（token）默认为 1000
        *   `parent_mode` 父分段的召回模式 `full-doc` 全文召回 / `paragraph` 段落召回
        *   `subchunk_segmentation` (object) 子分段规则
            *   `separator` 分段标识符，目前仅允许设置一个分隔符。默认为 `***`
            *   `max_tokens` 最大长度 (token) 需要校验小于父级的长度
            *   `chunk_overlap` 分段重叠指的是在对数据进行分段时，段与段之间存在一定的重叠部分（选填）
    
*   当知识库未设置任何参数的时候，首次上传需要提供以下参数，未提供则使用默认选项（你不需要考虑这块，我会提前准备好知识库）：
*   `retrieval_model`
    
    object
    
    检索模式
    
    *   `search_method` (string) 检索方法
        *   `hybrid_search` 混合检索
        *   `semantic_search` 语义检索
        *   `full_text_search` 全文检索
    *   `reranking_enable` (bool) 是否开启rerank
    *   `reranking_mode` (String) 混合检索
        *   `weighted_score` 权重设置
        *   `reranking_model` Rerank 模型
    *   `reranking_model` (object) Rerank 模型配置
        *   `reranking_provider_name` (string) Rerank 模型的提供商
        *   `reranking_model_name` (string) Rerank 模型的名称
    *   `top_k` (int) 召回条数
    *   `score_threshold_enabled` (bool)是否开启召回分数限制
    *   `score_threshold` (float) 召回分数限制
    
*   `embedding_model`
    
    string
    
    Embedding 模型名称
    
*   `embedding_model_provider`
    
    string
    
    Embedding 模型供应商
    

* * *
 索引方式选择高质量
`doc_form`选择父子分段`hierarchical_model` parent-child 模式
`process_rule`中 `mode`选择自动
pre_processing_rules` 先不进行预处理
 `segmentation` (object) 父分段规则就按照@@@@@，最大2000，子分段就按照/n分段，最大500
chunk_overlap允许重叠50token吧