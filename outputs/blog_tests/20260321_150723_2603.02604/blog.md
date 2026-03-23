# Heterogeneous Agent Collaborative Policy Optimization (HACPO): A Technical Overview

This blog post distills the key technical details from a recent paper on Heterogeneous Agent Collaborative Policy Optimization (HACPO), a novel reinforcement learning framework for fine-tuning multiple large language models (LLMs) of different sizes and capabilities simultaneously.

## Training & Evaluation Setup

The experiments were conducted using the **verl** framework. Key training parameters include:
*   **Dataset:** MATH.
*   **Model Context:** Max prompt length of 1024 tokens, max response length of 4096 tokens (extended to 8196 for complex evaluations like AIME2025).
*   **Optimization:** Learning rate of 1e-6, batch size of 128.
*   **Agents:** Models from the **Qwen3** (1.7B, 4B, 8B) and **Llama3.2** series were used, including base, distilled, and instruction-tuned variants.
*   **Infrastructure:** Training was performed on eight GPUs.

A core comparison is made against a **Resource-Equivalent Baseline (GSPO×2)**, which doubles the update frequency of a single-agent baseline to match HACPO's total computational cost.

## Core Algorithmic Concepts

HACPO builds upon recent advances in Reinforcement Learning from Human Feedback (RLHF), specifically Group Relative Policy Optimization (GRPO) and its successor, Group Sequence Policy Optimization (GSPO).

*   **GRPO/GSPO:** These are "critic-free" RL algorithms. They generate a group of responses for a single prompt and compute advantages *within* that group, eliminating the need for a separate value network. GSPO improves stability, especially for Mixture-of-Experts models, by using a sequence-level importance sampling ratio instead of a token-level one.
*   **HACPO's Innovation:** Standard knowledge distillation involves a one-way transfer from a strong "teacher" to a weak "student." HACPO reimagines this: multiple **heterogeneous agents** (models of different sizes) learn collaboratively as peers. They engage in self-exploration *and* learn from each other's generated responses concurrently.

## The Challenge: Heterogeneous Importance Sampling

A significant technical hurdle in multi-agent RL is importance sampling, used to stabilize policy updates. In single-agent settings (like GSPO), the sampling ratio is clipped tightly around 1.0.

In HACPO, this changes dramatically:
*   **Self-generated responses (`s_homo`)**: The importance sampling ratio remains stable and near 1.
*   **Cross-agent responses (`s_hete`)**: The ratio fluctuates unpredictably because the policies of different agents diverge.

This fluctuation means that as training progresses within a batch, the influence of cross-agent samples can become unstable if not properly managed.

## HACPO's Solution: Agent-Capability-Aware Estimation

To harness beneficial cross-agent learning while mitigating instability, HACPO introduces two key mechanisms:

1.  **Agent-Capability-Aware Advantage Estimator:** This computes a dynamic baseline for each agent by weighting rewards from *all* agents, not just its own. The weight for another agent's reward is a **capability ratio (`ω`)**, estimated via a moving average over recent performance.
2.  **Model Capability Discrepancy Coefficient (`α`)**: This parameter controls the mixing of gradients from self-generated and cross-agent responses. It's adaptively clipped to prevent unstable cross-agent gradients from dominating the update.

**Theoretical Guarantee:** Under a practical assumption that the capability ratio `ω` is estimated independently of the current batch's stochastic rewards, the paper proves that this coupled baseline provides an **unbiased estimate** of an agent's expected reward. This means that in expectation, learning from others does not introduce bias compared to learning only from oneself.

## Key Takeaways

*   **Collaborative Learning:** HACPO enables LLMs of different sizes to learn from each other simultaneously, moving beyond one-way knowledge distillation.
*   **Stability is Key:** Directly using samples from heterogeneous agents introduces unstable importance sampling ratios. HACPO addresses this with a capability-aware advantage estimator and adaptive gradient mixing.
*   **Theoretical Foundation:** The method provides an unbiased advantage estimate, ensuring the collaborative process is principled and not detrimental in expectation.
*   **Practical Design:** The framework includes careful hyperparameter tuning (e.g., clipping boundaries `δ` and `δ_step`) to balance learning from others with training stability.