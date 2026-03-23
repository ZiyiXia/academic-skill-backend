# MiroThinker: Advancing AI Reasoning with Targeted Exploration and Verification

This blog post summarizes key innovations and results from the MiroThinker research, which introduces new methods for improving the reasoning and exploration capabilities of large language models (LLMs) in complex, multi-step tasks.

## Optimizing Policy with Targeted Exploration

The core training objective uses **Group Relative Policy Optimization (GRPO)** paired with a novel **entropy control mechanism**. The goal is to balance finding correct solutions with following instructions, while preventing the model from becoming overconfident and ceasing to explore new ideas.

The reward for a given question \( x \) and a generated trajectory (sequence of reasoning steps) \( H \) is:
$$ R(x, H) = \alpha_{c} R_{\text{correct}}(H) - \alpha_{f} R_{\text{format}}(H) $$

GRPO works by sampling a group of \( G \) different reasoning trajectories for the same prompt. The advantage of one trajectory is calculated relative to the group's average reward:
$$ \hat{A}_{i} = R(x, H_{i}) - \frac{1}{G} \sum_{j=1}^{G} R(x, H_{j}) $$

The final training loss incorporates a dynamic penalty to maintain healthy exploration:
$$ \mathcal{L}_{\mathrm{GRPO}}(\theta)=\mathbb{E}_{x\sim\mathcal{D}}\mathbb{E}_{H\sim\pi_{\theta}}\left[\hat{A}(x,H)\log\pi_{\theta}(H\mid x)-\sum_{t=1}^{|H|}\beta_{\mathrm{KL}}(t,H)D_{\mathrm{KL}}\big(\pi_{\theta}(\cdot\mid s_{t})\parallel\pi_{\mathrm{ref}}(\cdot\mid s_{t})\big)\right] $$

The key innovation is the dynamic penalty coefficient \( \beta_{\mathrm{KL}}(t,H) \). It applies an extra penalty **only** to low-probability tokens within unsuccessful reasoning paths (where the advantage \( \hat{A} \) is negative). This specifically discourages the model from continuously driving down the likelihood of exploring novel tokens, stabilizing training and preventing premature convergence.

## Heavy-Duty Reasoning with Dual Verification

For the most challenging problems, the researchers developed **MiroThinker-H1**, a model that instantiates a "Heavy-duty Reasoning Mode." This mode systematically integrates verification into the reasoning process through two new components:

1.  **Local Verifier:** This operates at the step level. Under standard reasoning, an agent often follows the highest-probability next step, which can lead to habitual thinking traps on hard problems. The local verifier prompts the agent to explore more thoroughly and gather selective feedback, encouraging a broader search of the solution space.
2.  **Global Verifier:** This audits the complete reasoning chain. It leverages the fact that *verification is often easier than generation*. The system organizes all collected evidence; if it's insufficient, the agent is asked to resample or extend its reasoning rather than give a premature answer. Within a set compute budget, the final answer is the one backed by the most complete evidence.

## Experimental Results

The MiroThinker models were evaluated on a wide range of benchmarks testing agentic capabilities (web browsing, retrieval, multi-step reasoning) and professional-domain knowledge.

### Overall Agent Performance
MiroThinker-H1 established new state-of-the-art results on several major benchmarks:
*   **GAIA:** Scored **88.5**, surpassing the previous leader (OpenAI-GPT-5 at 76.4) by 12.1 points.
*   **BrowseComp / BrowseComp-ZH:** Achieved **88.2** and **84.4**, outperforming strong commercial agents like Gemini-3.1-Pro and Claude-4.6-Opus.
*   **SEAL-0:** Achieved a best-in-class score of **61.3**.

Notably, the smaller **MiroThinker-1.7-mini** (with only 3B activated parameters) performed competitively, even outperforming much larger models like GPT-5 on some benchmarks.

### Professional Domain Expertise
The models were tested on specialized benchmarks in science, finance, chemistry, and medicine.

![Table of professional-domain benchmark results](imgs/pdf0_img_in_table_551_702_1895_1296.jpg)

MiroThinker-H1 achieved top results on three out of four professional benchmarks:
*   **FrontierSci-Olympiad (Science): 79.0**
*   **FinSearchComp (Finance): 73.9**
*   **MedBrowseComp (Medicine): 56.5**

These results demonstrate robust performance on knowledge-intensive tasks across specialized fields.

### Long-Form Report Generation
Using an automated evaluation on 50 deep research queries, MiroThinker was assessed on generating long reports.

![Table of long report evaluation results](imgs/pdf0_img_in_table_718_485_1724_1233.jpg)

Key findings:
*   **State-of-the-Art Report Quality:** MiroThinker-H1 achieved the highest overall report quality score, outperforming specialized deep research agents from ChatGPT and Gemini.
*   **Strong Factual Grounding:** The MiroThinker series showed reliable factual accuracy, approaching the level of the strongest factuality-focused models.

## Key Takeaways

1.  **Dynamic Entropy Control is Crucial:** The targeted KL penalty on low-likelihood tokens in failing trajectories is a key innovation that sustains exploration and stabilizes RL training for language models.
2.  **Verification Augments Reasoning:** The Heavy-duty Reasoning Mode (MiroThinker-H1) shows that integrating explicit local and global verification steps can significantly improve performance on complex, long-horizon problems.
3.  **Strong and General Performance:** The MiroThinker series achieves state-of-the-art or highly competitive results across a broad spectrum of tasks, from general web agent benchmarks to specialized professional domains and long-form research report generation.
4.  **Efficiency Matters:** The compact MiroThinker-1.7-mini model demonstrates that effective scaling and algorithmic improvements can lead to highly capable models with a fraction of the activated parameters.