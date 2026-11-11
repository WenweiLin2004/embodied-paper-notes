# Embodied AI comparison dimensions

Select dimensions that change the user's decision; this is not a requirement to fill every field.

- **Task and embodiment**: manipulation/navigation/locomotion; robot model and degrees of freedom; sensor suite; action frequency; action space and control interface.
- **Learning setup**: demonstrations, trajectories and robot hours; pretraining sources; overlap with evaluation objects/environments; simulation data; fine-tuning and online interaction budget.
- **Evaluation split**: seen/unseen tasks, objects, language and scenes; cross-robot transfer; simulated versus physical execution; whether the same benchmark revision is used.
- **Outcome**: metric definition, higher/lower direction, success denominator, timeout/failure handling, number of trials and seeds, variance or confidence interval when reported.
- **Baseline fairness**: same training data and observation/action access; equivalent compute and adaptation budget; whether baseline results are rerun or quoted from another paper.
- **Deployment**: policy inference latency and hardware, closed/open-loop control, intervention assumptions, extra privileged state, failure recovery.
- **Mechanism and evidence**: model/data changes, ablation isolates, tested versus conjectured generalization, code/checkpoints and data availability.

Keep the published unit and measurement protocol. A normalized score requires an explicit calculation and compatible source definitions. A missing value is “not reported in the inspected material,” not zero. Absence of a statistically significant difference does not establish equivalence. Treat a claim of novelty as the authors' claim unless the search scope supports a broader assessment.
