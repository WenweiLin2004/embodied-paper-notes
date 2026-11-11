# Reproduction evidence checklist

For each relevant item, record **reported / available / checked / missing / ambiguous**, its source location, and the consequence for the target experiment. “Checked” requires an actual check, not a README statement.

## Artifacts and environment

- Official repository URL, commit/release, license and submodules.
- Language/framework versions, CUDA/driver requirements, OS and dependency lockfiles.
- Dataset version, download access, splits, preprocessing and normalization statistics.
- Checkpoint identity, training stage and compatible model/configuration.
- Robot/hand/sensor model, calibration, action space, control rate, simulator and assets.

## Training and evaluation

- Architecture and input/output conventions; optimizer, schedule, batch size and precision.
- Demonstration/interaction budget, random seeds, stopping rule and checkpoint selection.
- Evaluation scripts, environment seeds, resets and trial counts.
- Exact success metric and denominator, timeout/intervention rules and aggregation.
- Baseline settings, ablation changes, inference hardware and reported latency.

## A useful handoff

Name the paper result to target, the smallest check that would reveal a broken environment, and the earliest unknown that blocks a faithful reproduction. Preserve actual commands as sourced examples rather than pretending to have executed them. A successful smoke test is weaker evidence than reproducing the published metric; independently implemented results should be labeled separately from official-code results.
