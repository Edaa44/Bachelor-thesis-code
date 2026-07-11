# Numeric-to-Classical Planning Translation

**Bachelor thesis project**

This repository implements a compilation from bounded numeric planning
tasks to classical planning tasks, allowing numeric PDDL problems to be
solved by unmodified classical planners.

The underlying numeric PDDL-to-SAS translation is based on the numeric
Fast Downward translator developed for the
[IPC 2023 Numeric Track](https://ipc2023-numeric.github.io/), extended
here with an additional component (`numeric_ir`) that recovers a clean,
symbolic representation of numeric preconditions and effects from the
translator's internal finite-domain encoding. This repository then adds
a further translation stage that compiles the resulting numeric task
into a purely classical (propositional, finite-domain) SAS+ task,
solvable by any standard classical planner such as
[Fast Downward](https://www.fast-downward.org/).

 ## Requirements

- Python 3.10+
- A classical planner capable of reading plain SAS+ input, e.g. [Fast Downward](https://www.fast-downward.org/) (built separately; not included in this repository)

## Usage


### Batch (all registered instances)
on path src/translate

```bash
python3 translate.py
```

With no arguments, translates every instance registered in `ALL_BETA`
(currently `drone1`–`drone20` and `expedition1`–`expedition20`),
reading each domain/problem pair from `pddl/`, and writes one
`output_classical_<instance>.sas` per instance. Useful for local
testing of the full benchmark set without submitting a batch job.

Example domain/problem pairs are provided in `instances/`.


## How the pipeline runs the classical search

`run_pipeline.py` handles the entire process end to end for a single
instance: it translates the numeric PDDL task, then automatically
pipes the resulting classical SAS+ task into Fast Downward's search
component and records the result. You do not need to invoke the
search binary yourself — running

```bash
python3 run_pipeline.py drone1
```

performs translation and search in one step, writing
`output_classical_drone1.sas`, `sas_plan_drone1`, and
`results/drone1.json`.

Internally, this is equivalent to running:

```bash
/path/to/fast-downward/builds/release/bin/downward \
    --search "astar(blind())" \
    --internal-plan-file sas_plan_drone1 \
    < output_classical_drone1.sas
```
**Output:** `run_pipeline.py` automatically parses the search
binary's stdout and records status (`solved`/`unsolvable`/`timeout`),
search time, peak memory, states expanded, and plan length into
`results/<instance>.json`. Running `report.py` afterward consolidates
these across every evaluated instance into `results.csv`, a summary
table, and scaling plots.

## Notes

Numeric variable bounds must be supplied manually per instance (see
`ALL_BETA` in `translate.py`), since the numeric SAS+ input format does
not itself encode a bound for numeric variables. See the thesis text
for a discussion of this design choice and its limitations.


