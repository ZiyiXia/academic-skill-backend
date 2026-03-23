# OpenClaw-RL: Train Any Agent Simply by Talking

**Authors:** Yinjie Wang, Xuyang Chen, Xiaolong Jin, Mengdi Wang, Ling Yang

Every time an AI agent acts—sending a message, running a command, clicking a button—it receives a **next-state signal**. This could be a user's reply, a tool's output, or a change in a GUI. While crucial for deciding the next action, this signal is typically discarded after use. The authors of OpenClaw-RL argue this is a massive waste: these signals contain free, implicit feedback on the agent's performance.

OpenClaw-RL is a new framework built on a simple, powerful idea: **next-state signals are a universal, live learning source.** Whether from a personal conversation, a terminal session, or a coding task, these signals can all be used to train the same policy in the same continuous loop.

## The Core Insight: Two Forms of Wasted Signal

The framework recovers two key types of information from the next-state signal (`s_{t+1}`) that follows an action (`a_t`):

1.  **Evaluative Signals:** Does the signal indicate the action was good or bad? (e.g., a user re-asking a question suggests dissatisfaction). This is converted into a scalar **reward**.
2.  **Directive Signals:** Does the signal specify *how* the action should have been different? (e.g., a user says, "You should have checked the file first"). This provides rich, **token-level guidance** for improvement.

## System Architecture: Fully Decoupled and Asynchronous

![OpenClaw-RL Infrastructure Overview](imgs/pdf0_img_in_image_box_277_1780_2132_2469.jpg)
*Figure 1: The OpenClaw-RL infrastructure. It handles streams from both personal agents (on user devices) and general agents (hosted on cloud services) through four independent, asynchronous components.*

The system is designed for zero interruption to live serving. Its four components run in parallel:
1.  **Policy Serving (SGLang):** Handles live user/agent requests.
2.  **Environment Server:** Manages interactions (user devices for personal agents, cloud-hosted simulators for general agents).
3.  **PRM/Judge:** Evaluates actions and extracts hints from the next-state signal.
4.  **Policy Training (Megatron):** Continuously updates the model with new data.

This decoupling means the model can learn from its own live interactions without any pause in service.

## Two Complementary Learning Methods

OpenClaw-RL provides two ways to learn from next-state signals, which can be combined for best results.

### 1. Binary RL: Learning from Evaluative Signals
A Process Reward Model (PRM) judges the quality of an action (`a_t`) based on the next state (`s_{t+1}`), outputting a score: `+1` (good), `-1` (bad), or `0` (neutral). Multiple independent judge calls are made, and the majority vote becomes the reward. This provides a dense, step-by-step training signal, especially vital for long-horizon tasks.

**Training Objective:** A standard PPO-style objective is used with this scalar reward as the advantage.

### 2. Hindsight-Guided On-Policy Distillation (OPD): Learning from Directive Signals
This method extracts richer, directional information. When the PRM detects a corrective hint in `s_{t+1}`, it distills that hint into a concise, actionable instruction.

*   **Process:** The hint is appended to the original user prompt, creating an "enhanced" context. The same policy model is then run on this enhanced context, generating a new, improved token distribution for the original action.
*   **Supervision:** The difference between the log-probabilities of the original response and the "hint-informed" response creates a **token-level advantage signal** (`A_t`). This tells the model exactly which tokens to reinforce or suppress.

### 3. The Combined Approach
The two methods are complementary. Binary RL provides broad, coarse-grained feedback on every turn. OPD provides high-resolution, targeted corrections but only on turns with clear directive signals. They can be combined in a weighted advantage function:
`A_t = w_binary * r_final + w_opd * (log π_teacher(a_t|s_enhanced) - log π(a_t|s_t))`

## Experimental Validation

The framework was tested in two tracks using simulated interactions.

### Personal Agent Track
A personal AI assistant (OpenClaw) was optimized based on simulated user conversations.
*   **Student Scenario:** The agent learned to avoid AI-like phrasing and adopt a more natural style when helping with homework.
*   **Teacher Scenario:** The agent learned to give more specific and friendly feedback when grading assignments.

**Key Finding:** The combined Binary RL + OPD method achieved the strongest optimization. OPD provided higher-quality signal but was slower due to sample sparsity, while Binary RL alone offered only marginal gains.

![Optimization Results](imgs/pdf0_img_in_image_box_255_339_2116_843.jpg)
*Figure 2: Simulation results showing OpenClaw's improvement over a small number of interactions when using the combined optimization method.*

### General Agent Track
The same infrastructure was applied to train specialized agents in four domains:
*   **Terminal Agents** (command-line interaction)
*   **GUI Agents** (visual interface interaction)
*   **SWE Agents** (software engineering/coding)
*   **Tool-Call Agents** (using external tools/APIs)

**Key Finding:** The framework successfully supported scalable RL training across all these diverse settings. Furthermore, integrating step-wise process rewards with final outcome rewards led to stronger performance than using outcome rewards alone.

![General Agent Performance](imgs/pdf0_img_in_chart_box_248_335_712_804.jpg) ![General Agent Performance](imgs/pdf0_img_in_chart_box_730_334_1182_802.jpg) ![General Agent Performance](imgs/pdf0_img_in_chart_box_1191_333_1659_802.jpg) ![General Agent Performance](imgs/pdf0_img_in_chart_box_1674_333_2129_801.jpg)
*Figure 4: The framework enables RL training for general agents across terminal, GUI, SWE, and tool-call settings.*

## Key Takeaways

*   **Live Learning is Possible:** AI agents can continuously improve from the natural feedback (next-state signals) they receive during normal operation, without needing pre-collected datasets.
*   **A Unified Framework:** OpenClaw-RL demonstrates that a single training system can handle diverse agent types—from personal chatbots to coding and GUI agents—by treating all their interactions as universal learning signals.
*   **Signal Quality Matters:** Next-state signals contain both a simple score (evaluative) and rich corrective instructions (directive). Recovering both through Binary RL and Hindsight-Guided OPD provides a more powerful and efficient training signal than either method alone.
*   **Built for Real-World Use:** The fully asynchronous, decoupled architecture allows for continuous learning without interrupting the live service, making it practical for real-world deployment.