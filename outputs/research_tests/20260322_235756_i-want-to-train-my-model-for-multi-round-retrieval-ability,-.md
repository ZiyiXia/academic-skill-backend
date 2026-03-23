# Report on Datasets for Training Multi-Round Retrieval Ability (Post-2022)

## Answer Overview

This report addresses the request for datasets suitable for training models with multi-round retrieval ability, specifically excluding classic datasets released before 2022. Based on the provided papers, several candidate datasets and benchmarks have been identified that were introduced in 2023 or later, focusing on conversational, multi-turn, and retrieval-augmented scenarios. The evidence is **moderately strong** for identifying relevant datasets, though direct availability details (e.g., download links, licensing) are not explicitly provided in the abstracts. The candidates span reasoning-focused conversational retrieval, emotionally-rich dialogues, retrieval-augmented generation (RAG) benchmarks, music discovery dialogues, and cross-lingual retrieval collections. This analysis synthesizes the retrieved papers to provide actionable recommendations.

## Candidate Options

The following datasets and benchmarks, all released in 2023 or later, are relevant for multi-round retrieval training:

1. **RECOR (Reasoning-focused Multi-turn Conversational Retrieval Benchmark)**  
   - **Release Date:** 2026-01-09 (anticipated future release; included due to relevance).  
   - **Focus:** Combines multi-turn conversation with reasoning-intensive retrieval.  
   - **Size:** 707 conversations (2,971 turns) across eleven domains.  
   - **Key Feature:** Uses a Decomposition-and-Verification framework to create fact-grounded dialogues with explicit retrieval reasoning per turn.

2. **DeepDialogue**  
   - **Release Date:** 2025-05-26.  
   - **Focus:** Multi-turn emotionally-rich spoken dialogues across modalities.  
   - **Size:** 40,150 multi-turn dialogues spanning 41 domains, incorporating 20 distinct emotions.  
   - **Key Feature:** Multimodal (not text-only), with coherent emotional progressions; generated via LLMs and filtered for quality.

3. **CORAL (Benchmarking Multi-turn Conversational Retrieval-Augmentation Generation)**  
   - **Release Date:** 2024-10-30.  
   - **Focus:** Multi-turn conversational RAG in realistic information-seeking settings.  
   - **Size:** Large-scale, derived from Wikipedia; supports open-domain coverage and topic shifts.  
   - **Key Feature:** Evaluates three core tasks: passage retrieval, response generation, and citation labeling.

4. **LP-MusicDialog**  
   - **Release Date:** 2024-11-11.  
   - **Focus:** Music discovery dialogue generation via human intent analysis and LLMs.  
   - **Size:** Created from the Million Song dataset; volume and quality emphasized over prior limited datasets.  
   - **Key Feature:** Integrates user intents, system actions, and musical attributes for seamless multi-turn conversation.

5. **NeuCLIRBench**  
   - **Release Date:** 2025-11-18 (anticipated future release; included due to relevance).  
   - **Focus:** Monolingual, cross-language, and multilingual information retrieval evaluation.  
   - **Size:** 250,128 judgments across ~150 queries for monolingual/cross-language tasks and ~100 for multilingual retrieval.  
   - **Key Feature:** Combines TREC NeuCLIR track topics (2022–2024); supports multiple retrieval scenarios with documents in Chinese, Persian, Russian, and English.

**Note:** Two papers (Iter-RetGen and In-Context RALM) discuss methods for iterative retrieval-generation synergy and in-context retrieval-augmented LMs but do not introduce new datasets; they are methodological contributions that could inform training approaches.

## Evidence Comparison

The evidence from the papers is **descriptive but incomplete** regarding dataset accessibility. All candidates are post-2022 and address multi-turn or retrieval aspects, but their suitability varies:

- **RECOR** and **CORAL** are directly designed for **conversational retrieval**, with RECOR emphasizing reasoning and CORAL focusing on RAG. Both include multi-turn interactions and retrieval tasks, making them strong candidates for training retrieval ability in dialogue contexts.
- **DeepDialogue** offers **emotional and multimodal richness**, which could enhance retrieval models in affective computing or spoken dialogue systems, but its primary focus is not retrieval-specific.
- **LP-MusicDialog** is **domain-specific (music)**, ideal for training retrieval in niche applications, but may lack generalizability to broader multi-round retrieval.
- **NeuCLIRBench** is **cross-lingual and evaluation-focused**, useful for training retrieval in multilingual settings, though it may not emphasize conversational turns.
- **Iter-RetGen** and **In-Context RALM** provide **methodological insights** (e.g., iterative retrieval-generation synergy) that could complement dataset use, but they are not datasets themselves.

Strengths of the evidence include clear release dates, sizes, and focuses. Weaknesses include lack of details on dataset availability (e.g., GitHub repositories, licensing), which may require further investigation by the user.

## Recommendations

Based on the analysis, the following recommendations are prioritized for training multi-round retrieval ability:

1. **Primary Recommendation: CORAL**  
   - **Why:** It is a large-scale, realistic benchmark specifically for multi-turn conversational RAG, covering open-domain information seeking with tasks directly relevant to retrieval (passage retrieval, citation labeling). Its 2024 release ensures modernity.
   - **Use Case:** Train models for conversational search assistants or chatbots requiring retrieval over multiple turns.

2. **Secondary Recommendation: RECOR**  
   - **Why:** Focuses on reasoning-intensive retrieval in conversations, with explicit retrieval reasoning per turn. The reported performance gains (history+reasoning doubling retrieval performance) suggest it is effective for training complex retrieval models.
   - **Use Case:** Train models where logical reasoning and fact-grounded dialogues are critical, such as technical support or educational systems.

3. **Tertiary Recommendation: LP-MusicDialog**  
   - **Why:** If the application domain is music discovery, this dataset provides rich, intent-driven dialogues for multi-turn retrieval training. Its LLM-based generation ensures quality and volume.
   - **Use Case:** Train retrieval models for conversational music recommendation systems.

4. **Additional Considerations:**  
   - For **multilingual retrieval**, consider NeuCLIRBench once available, as it offers diverse language pairs and robust evaluation.  
   - For **emotional or multimodal retrieval**, DeepDialogue could be adapted, though retrieval is not its primary focus.  
   - Incorporate **methodological insights** from Iter-RetGen and In-Context RALM to design training pipelines that synergize retrieval and generation iteratively.

## Caveats

- **Availability Uncertainty:** The papers do not explicitly state if datasets are publicly released; users may need to contact authors or monitor platforms like GitHub or Hugging Face for access.
- **Temporal Scope:** Two datasets (RECOR and NeuCLIRBench) have future release dates (2026 and 2025), so they may not be immediately available for training.
- **Task Alignment:** Some datasets (e.g., DeepDialogue) are not retrieval-specific; adapting them may require additional annotation or preprocessing.
- **Evidence Gaps:** The abstracts lack details on dataset structure (e.g., query-passage pairs, conversation logs), licensing, and baseline implementations, which could affect usability.
- **Generalization:** Domain-specific datasets (e.g., LP-MusicDialog) may not transfer well to other domains without fine-tuning or data augmentation.

In summary, CORAL and RECOR are the most promising candidates for multi-round retrieval training, given their direct focus and post-2022 release. Users should verify accessibility and consider complementing dataset use with iterative retrieval methods from the literature.