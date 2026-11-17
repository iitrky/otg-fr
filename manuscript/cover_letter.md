---
title: "Cover Letter"
---

::: {custom-style="Affiliation"}
Department of Computer Science and Engineering, Saveetha Engineering College, Chennai, Tamil Nadu, India
:::

17 November 2026

The Editor-in-Chief\
*Journal of Electrical Engineering & Technology*\
Springer Nature

**Subject:** Submission of an original research article entitled "Grid Frequency as the Aggregation Channel for Federated Restoration of Islanded Microgrids"

Dear Editor-in-Chief,

We are pleased to submit the manuscript entitled **"Grid Frequency as the Aggregation Channel for Federated Restoration of Islanded Microgrids"** for consideration as an Original Article in the *Journal of Electrical Engineering & Technology*.

After extreme weather events, distribution feeders are increasingly restored as islands energized by battery storage and photovoltaic generation, while the telecommunication networks that should coordinate these islands fail in the same event. Our manuscript shows that an energized island can coordinate itself. Grid-forming inverters under frequency droop settle to a common frequency that equals a stiffness-weighted sum of all inverter set-points. The electrical network therefore physically computes the aggregates required by federated learning and dual decomposition, so no communication link or central server is needed.

The main contributions of the work are as follows.

1. **Concept.** The droop steady state of an alternating-current island is used as an analogue aggregation server for federated algorithms, without the channel model, time slots or per-zone messages that droop-signalling ("power talk") schemes require.
2. **Ratio-coded droop aggregation with analysis.** We prove that ratio decoding is exact for any unknown droop stiffness and network (Proposition 1). We show that ordering Walsh codes by their polynomial drift order cancels load and photovoltaic ramps up to the fourth degree, whereas the usual ordering rejects only constants (Proposition 2). We also derive a closed-form decoding-error law with its validity range, which matches simulation to within 9% (Proposition 3), and an excursion bound.
3. **Over-the-grid federated restoration.** Zones learn cold-load pick-up federatively and agree on an island-wide energy price through the grid frequency; ergodic averaging of the price removes the oscillation of the dual update and cuts load re-interruptions fourfold.
4. **Rigorous comparison and validation.** A factorial comparison with time-slotted power talk shows a sixfold lower decoding error in AC power flow when the droop stiffness is unknown (0.041 against 0.246). One hundred paired 24-hour restorations on an islanded IEEE 33-bus feeder give 96.5% of the priority-weighted energy of a full-information coordinator and 99.95% of critical-load energy with 9.6 re-interruptions per day, against 78.8%, 88.5% and 18.8 for the best communication-free practice. We also report a sensitivity study of every design parameter, photovoltaic-ramp stress tests, and paired statistics with bootstrap confidence intervals, effect sizes and Holm correction.

We believe the manuscript fits the scope of the journal in power systems, distribution automation and smart-grid resilience. It will interest researchers and utility engineers working on service restoration, grid-forming inverters and the operation of microgrids during communication blackouts.

**Declarations.** We confirm that:

* the manuscript is original, has not been published previously, and is not under consideration for publication elsewhere;
* all authors have approved the manuscript and agree with its submission to the *Journal of Electrical Engineering & Technology*;
* the authors have no competing interests to declare;
* the study involves no human participants or animals, and no previously published figures or tables requiring permission are reproduced;
* the manuscript has been anonymized for double-blind review, and author information is provided only on the separate title page;
* in accordance with the journal's policy, the use of a large language model is documented in Section 4.5 of the manuscript, and the authors take full responsibility for the content;
* all code and data supporting the findings are openly available at https://github.com/iitrky/otg-fr and are also supplied as Online Resource 1 (an anonymized archive for reviewers).

**Submitted files:** anonymized manuscript (Word), title page with author information and declarations (Word), Fig1–Fig9 (600 dpi TIFF) and Online Resource 1 (ESM_1.zip).

Thank you for considering our manuscript. We look forward to hearing from you.

Yours sincerely,

**Arul Dalton G** (Corresponding author)\
Department of Computer Science and Engineering\
Saveetha Engineering College, Chennai, Tamil Nadu, India\
E-mail: aruldalton@saveetha.ac.in\
ORCID: 0000-0002-5981-7176

On behalf of all authors: Arul Dalton G and Marisargunam S
