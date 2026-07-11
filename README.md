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
- CMake and a C++ build toolchain (for the numeric translator's compiled components)
- A classical planner capable of reading plain SAS+ input, e.g. [Fast Downward](https://www.fast-downward.org/) (built separately; not included in this repository)

## Compile

Install CPLEX Optimization Studio 22.1.1 in `/opt/ibm/ILOG/CPLEX_Studio2211`.
Then, run the script with the root privilege.

```bash
./compile
```

## Usage

From `/translate`:

### Single instance

```bash
python3 translate.py <domain.pddl> <problem.pddl>
```

Parses the given numeric PDDL domain and problem, translates them into
a numeric SAS+ task, and compiles the result into a classical SAS+
task, written to `output_classical_<instance>.sas`. This is the mode
used when running on a grid/cluster, where each job translates exactly
one instance.

### Batch (all registered instances)

```bash
python3 translate.py
```

With no arguments, translates every instance registered in `ALL_BETA`
(currently `drone1`–`drone20` and `expedition1`–`expedition20`),
reading each domain/problem pair from `pddl/`, and writes one
`output_classical_<instance>.sas` per instance. Useful for local
testing of the full benchmark set without submitting a batch job.

Example domain/problem pairs are provided in `instances/`.

## Solving the Output

Run_pipeline.py

to be completed


To solve the resulting classical task, pipe it into a classical
planner's search component, e.g.:

```bash
/path/to/fast-downward/builds/release/bin/downward \
    --search "astar(blind())" \
    --internal-plan-file sas_plan \
    < output_classical_<instance>.sas
```

## Notes

Numeric variable bounds must be supplied manually per instance (see
`ALL_BETA` in `translate.py`), since the numeric SAS+ input format does
not itself encode a bound for numeric variables. See the thesis text
for a discussion of this design choice and its limitations.


