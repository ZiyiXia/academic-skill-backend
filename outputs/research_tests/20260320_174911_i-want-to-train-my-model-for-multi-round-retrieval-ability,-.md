# I want to train my model for multi-round retrieval ability, what datasets can I use? I don't want those classic datasets released before 2022.

## Question and Scope
The user asks: I want to train my model for multi-round retrieval ability, what datasets can I use? I don't want those classic datasets released before 2022.

The working goal for this run is: Investigate the research question: I want to train my model for multi-round retrieval ability, what datasets can I use? I don't want those classic datasets released before 2022.. The analysis below uses retrieved papers and any successful paper inspections to identify the strongest candidates, explain why they matter, and separate promising options from weaker or older alternatives.

## Candidate Landscape
RECOR: Reasoning-focused Multi-turn Conversational Retrieval Benchmark (2601.05461, 2026-01-09) is relevant because Existing benchmarks treat multi-turn conversation and reasoning-intensive retrieval separately, yet real-world information seeking requires both. To bridge this gap, we present a benchmark for reasoning-based conversational information retrieval comprising 707 conversations (2,971 turns) across eleven domains. To ensure quality, our Decomposition-and-Verific

DeepDialogue: A Multi-Turn Emotionally-Rich Spoken Dialogue Dataset (2505.19978, 2025-05-26T13:37:10Z) is relevant because Recent advances in conversational AI have demonstrated impressive capabilities in single-turn responses, yet multi-turn dialogues remain challenging for even the most sophisticated language models. Current dialogue datasets are limited in their emotional range, domain diversity, turn depth, and are predominantly text-only, hindering progress in developing mo

CORAL: Benchmarking Multi-turn Conversational Retrieval-Augmentation Generation (2410.23090, 2024-10-30T15:06:32Z) is relevant because Retrieval-Augmented Generation (RAG) has become a powerful paradigm for enhancing large language models (LLMs) through external knowledge retrieval. Despite its widespread attention, existing academic research predominantly focuses on single-turn RAG, leaving a significant gap in addressing the complexities of multi-turn conversations found in real-world app

Music Discovery Dialogue Generation Using Human Intent Analysis and Large Language Models (2411.07439, 2024-11-11T23:40:45Z) is relevant because A conversational music retrieval system can help users discover music that matches their preferences through dialogue. To achieve this, a conversational music retrieval system should seamlessly engage in multi-turn conversation by 1) understanding user queries and 2) responding with natural language and retrieved music. A straightforward solution would be a 

Enhancing Retrieval-Augmented Large Language Models with Iterative Retrieval-Generation Synergy (2305.15294, 2023-05-24T16:17:36Z) is relevant because Large language models are powerful text processors and reasoners, but are still subject to limitations including outdated knowledge and hallucinations, which necessitates connecting them to the world. Retrieval-augmented large language models have raised extensive attention for grounding model generation on external knowledge. However, retrievers struggle to

In-Context Retrieval-Augmented Language Models (2302.00083, 2023-01-31T20:26:16Z) is relevant because Retrieval-Augmented Language Modeling (RALM) methods, which condition a language model (LM) on relevant documents from a grounding corpus during generation, were shown to significantly improve language modeling performance. In addition, they can mitigate the problem of factually inaccurate text generation and provide natural source attribution mechanism. Exi

Active Retrieval Augmented Generation (2305.06983, 2023-05-11T17:13:40Z) is relevant because Despite the remarkable ability of large language models (LMs) to comprehend and generate language, they have a tendency to hallucinate and create factually inaccurate output. Augmenting LMs by retrieving information from external knowledge resources is one promising solution. Most existing retrieval augmented LMs employ a retrieve-and-generate setup that onl

NeuCLIRBench: A Modern Evaluation Collection for Monolingual, Cross-Language, and Multilingual Information Retrieval (2511.14758, 2025-11-18) is relevant because To measure advances in retrieval, test collections with relevance judgments that can faithfully distinguish systems are required. This paper presents NeuCLIRBench, an evaluation collection for cross-language and multilingual retrieval. The collection consists of documents written natively in Chinese, Persian, and Russian, as well as those same documents mach

## Evidence Review
No direct paper-level evidence was captured beyond search metadata.

## Recommendations
RECOR: Reasoning-focused Multi-turn Conversational Retrieval Benchmark (2601.05461) should be treated as a priority candidate because Existing benchmarks treat multi-turn conversation and reasoning-intensive retrieval separately, yet real-world information seeking requires both. To bridge this gap, we present a benchmark for reasoning-based conversational information retrieval comprising 707 conversations (2,971 turns) across eleven domains. To ensur

DeepDialogue: A Multi-Turn Emotionally-Rich Spoken Dialogue Dataset (2505.19978) should be treated as a priority candidate because Recent advances in conversational AI have demonstrated impressive capabilities in single-turn responses, yet multi-turn dialogues remain challenging for even the most sophisticated language models. Current dialogue datasets are limited in their emotional range, domain diversity, turn depth, and are predominantly text-o

CORAL: Benchmarking Multi-turn Conversational Retrieval-Augmentation Generation (2410.23090) should be treated as a priority candidate because Retrieval-Augmented Generation (RAG) has become a powerful paradigm for enhancing large language models (LLMs) through external knowledge retrieval. Despite its widespread attention, existing academic research predominantly focuses on single-turn RAG, leaving a significant gap in addressing the complexities of multi-tu

Music Discovery Dialogue Generation Using Human Intent Analysis and Large Language Models (2411.07439) should be treated as a priority candidate because A conversational music retrieval system can help users discover music that matches their preferences through dialogue. To achieve this, a conversational music retrieval system should seamlessly engage in multi-turn conversation by 1) understanding user queries and 2) responding with natural language and retrieved music

Enhancing Retrieval-Augmented Large Language Models with Iterative Retrieval-Generation Synergy (2305.15294) should be treated as a priority candidate because Large language models are powerful text processors and reasoners, but are still subject to limitations including outdated knowledge and hallucinations, which necessitates connecting them to the world. Retrieval-augmented large language models have raised extensive attention for grounding model generation on external kn

## Caveats and Next Steps
This report was assembled from partial evidence. If a production decision depends on it, the next step should be to read more recent candidate papers in depth, verify year and task formulation directly, and compare annotation schema, evaluation protocol, and licensing.