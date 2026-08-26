# CARLA Safety Agent

An original, risk-directed scenario generation agent for CARLA 0.9.16. It borrows
the useful architectural idea of task packets, adapters, execution and evidence
from GameFactory-3A, but defines a safety-specific scenario model, sampler,
oracles and CARLA runtime boundary.

## What the MVP does

- Generates deterministic `cut_in`, `hard_brake`, and `occluded_crossing` families.
- Biases samples toward parameter boundaries instead of producing ordinary traffic.
- Runs CARLA in synchronous fixed-step mode.
- Records distance/TTC traces and collision events.
- Ranks runs by risk and saves fully reproducible scenario specifications.
- Imports no CARLA code during offline generation or testing.

## Use on this machine

The existing CARLA virtual environment has been verified to load `carla.Client`.
Use it directly; a native-extension wheel cannot be imported by merely adding
the compressed `.whl` file to `PYTHONPATH`.

```bash
cd /home/moresweet/Documents/Codex/2026-08-26/gi/outputs/carla-safety-agent
PYTHONPATH=src /home/moresweet/carla/.venv/bin/python -m carla_safety_agent.cli --help
```

## Generate scenarios offline

```bash
PYTHONPATH=src /home/moresweet/carla/.venv/bin/python -m carla_safety_agent.cli generate \
  --family hard_brake --map Town04 --count 25 --seed 42 \
  --output runs/hard_brake/specs.json
```

## Execute against CARLA

Start the existing CARLA server separately, then run:

```bash
PYTHONPATH=src /home/moresweet/carla/.venv/bin/python -m carla_safety_agent.cli run \
  runs/hard_brake/specs.json \
  --host 127.0.0.1 --port 2000 --output-dir runs/hard_brake/evidence
```

The output contains `results.json` sorted by risk plus a per-scenario trace.

The agent loop is: define a scenario family and parameter envelope, generate a
boundary-biased campaign, execute it through the narrow CARLA adapter, evaluate
each trace with explicit oracles, rank critical evidence, then use retained
specifications as the reproducible seed population for the next campaign. This
separation is intentional: an LLM may propose families and constraints, but it
does not invent simulator measurements or overwrite oracle evidence.

## Research extension path

The next layer should add map-relative spawn constraints instead of raw spawn
indices, route-conflict geometry, sensor recording, OpenSCENARIO export, adaptive
search (cross-entropy/Bayesian/CMA-ES), minimisation of discovered failures, and
an ADS-under-test interface. Generated visual assets must remain separate from
ground-truth collision, semantic and dynamics assets.

## Safety interpretation

The included TTC is a constant-velocity online surrogate. It is intentionally
labelled and must not be treated as a formal RSS proof. A research claim should
name the tested ADS, Operational Design Domain, simulator version, seeds,
scenario distributions and oracle limitations.
