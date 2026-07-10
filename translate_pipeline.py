"""
Full pipeline: numeric SAS file -> NumericTask -> grounded
classical SAS (this) -> Fast Downward SASTask output.

Bounds (beta) are NOT in the numeric SAS file (per supervisors advice,
they're supplied manually here as a plain dict: {var_name: (lower, upper)}).
"""
from dataclasses import dataclass
from itertools import product
from typing import Dict, List, Tuple

import ir_task
from numeric_sas_reader import parse_numeric_sas, LinearExpr


@dataclass(frozen=True)
class LinearConstraint:
    coeffs: Dict[int, int]   # numeric var index -> coefficient
    op: str                  # '<=', '>=', '==', '<', '>'
    bound: int                # right-hand-side constant (after moving to RHS)

    def satisfied_by(self, nu: List[int]) -> bool:
        lhs = sum(k * nu[i] for i, k in self.coeffs.items())
        return {'<=': lhs <= self.bound,
                '>=': lhs >= self.bound,
                '==': lhs == self.bound,
                '<': lhs < self.bound,
                '>': lhs > self.bound}[self.op]


@dataclass
class NumericAction:
    name: str
    pre_p: List[Tuple[int, int]]          # (var, val) pairs
    pre_n: List[LinearConstraint]
    eff_p: List[Tuple[int, int]]          # (var, target_val) pairs
    eff_n: Dict[int, int]                  # numeric var index -> additive delta
    eff_assign: Dict[int, int] = None      # numeric var index -> constant value
    cost: int = 1

    def __post_init__(self):
        if self.eff_assign is None:
            self.eff_assign = {}


@dataclass
class NumericTask:
    prop_var_names: List[str]
    prop_domains: List[List[str]]          # value labels per prop var
    num_var_names: List[str]
    beta: Dict[int, Tuple[int, int]]       # numeric var index -> (l, u)
    actions: List[NumericAction]
    I_prop: List[int]                      # value index per prop var
    I_num: List[int]                       # value per numeric var
    G_prop: List[Tuple[int, int]]
    G_num: List[LinearConstraint]          # equality-only for this translation
    metric: bool = True


def resolve_beta(num_var_names: List[str], beta_by_name: Dict) -> Dict[int, Tuple[int, int]]:
    """Maps numeric var names to their bound, keyed by index in beta if a
    name is used more than once ( e.g. sled_supplies(s0) and sled_supplies(s1)
    both reported simply as 'sled_supplies' in dataset expedition). In that case, beta_by_name
    must provide the bound keyed by the variable's integer position
    instead (0-based, matching enumerate(num_var_names)); a plain name
    key is rejected outright for ambiguous names rather than silently
    picked, since that risk of misassigning one sled's bound to another's
    variable is a failure this translation should not produce."""
    from collections import Counter
    name_counts = Counter(num_var_names)

    beta = {}
    for i, name in enumerate(num_var_names):
        if name_counts[name] > 1:
            if i in beta_by_name:
                beta[i] = beta_by_name[i]
            elif name in beta_by_name:
                raise ValueError(
                    f"numeric var index {i} (name '{name}') is ambiguous: "
                    f"'{name}' is used by {name_counts[name]} different numeric "
                    f"variables, so a bound keyed by name alone cannot be assigned "
                    f"safely. Supply the bound keyed by index {i} instead, "
                    f"e.g. beta_by_name[{i}] = (lower, upper)."
                )
            else:
                for i, nv in enumerate(ir_task.numeric_variables.variable_names):
                    print(i, nv.symbol, getattr(nv, 'args', 'NO ARGS ATTR'))
                raise ValueError(
                    f"no manual bound supplied for numeric var index {i} "
                    f"(ambiguous name '{name}', appears {name_counts[name]} times "
                    f"-- supply it keyed by index {i}, not by name)"
                )
        else:
            if name not in beta_by_name and i not in beta_by_name:
                raise ValueError(f"no manual bound supplied for numeric var '{name}'")
            beta[i] = beta_by_name.get(i, beta_by_name.get(name))
    return beta


def classify_effect(target_var, coeffs: Dict[int, int], const, beta: Dict[int, Tuple[int, int]]):
    """Classifies a parsed effect expression on target_var into either an
    additive delta or a constant assignment, folding in any OTHER
    variable referenced in the expression if and only if  that other
    variable is frozen (beta[other][0] == beta[other][1], i.e. it can
    never actually change, such as an item's fixed weight). 
    This handles effects like 'current_load := current_load + weight(item)', where
    weight(item) is a per-item constant rather than a literal number in
    the source file, without requiring the delta to be a literal constant.

    Returns ('delta', value) or ('assign', value). Raises
    NotImplementedError if the expression depends on a variable that can
    actually vary, since that is a genuine cross-variable effect this
    translation does not support."""
    if coeffs.get(target_var, 0) == 1 and len(coeffs) == 1:
        return ('delta', int(const))

    if len(coeffs) == 0:
        return ('assign', int(const))

    if coeffs.get(target_var, 0) == 1 and len(coeffs) == 2:
        other = next(v for v in coeffs if v != target_var)
        l, u = beta[other]
        if l == u:
            # other is frozen at value l -- fold it into a concrete delta
            return ('delta', int(const) + int(coeffs[other]) * l)
        raise NotImplementedError(
            f"effect on var {target_var} depends on numeric var {other}, "
            f"which is not frozen under the supplied bound {beta[other]} "
            f"-- this translation only supports effects that reference "
            f"other variables when those variables are compile-time "
            f"constants (frozen, lower bound == upper bound)"
        )

    raise NotImplementedError(
        f"effect on var {target_var} is neither a pure additive delta, "
        f"a pure constant assignment, nor an additive delta folding in "
        f"exactly one frozen co-variable (got coeffs={coeffs}, const={const})"
    )

_IR_COMP_MAP = {'=': '==', '==': '==', '<=': '<=', '>=': '>=', '<': '<', '>': '>'}  # '!=' unsupported


def _ir_condition_to_constraint(cond) -> LinearConstraint:
    """Converts a numeric_ir LinearCondition (with .expr.coefficients,
    .expr.constant, .comp) into our LinearConstraint."""
    if cond.comp not in _IR_COMP_MAP:
        raise NotImplementedError(
            f"unsupported comparator '{cond.comp}' in numeric condition "
            f"(only '=', '<=', '>=', '<', '>' are supported by this translation)"
        )
    coeffs = {v: int(k) for v, k in cond.expr.coefficients.items()}
    bound = -int(cond.expr.constant)
    return LinearConstraint(coeffs, _IR_COMP_MAP[cond.comp], bound)


def _strip_op_name_parens(name: str) -> str:
    """IRTask carries operator names with surrounding parens, e.g.
    '(buy-laptop)', matching the convention its own .output() strips via
    name[1:-1]. We do the same here so names look like plain action names."""
    if len(name) >= 2 and name[0] == '(' and name[-1] == ')':
        return name[1:-1]
    return name


def ir_task_to_numeric_task(ir_task, beta_by_name: Dict[str, Tuple[int, int]]) -> NumericTask:
    """Builds a NumericTask directly from an in-memory IRTask instance,
    with no file I/O and no text parsing. IRTask has already resolved
    derived/comparison-proxy variables and remapped everything to dense,
    relevant-only indices, so this is simpler than the text-parsing path."""

    # -- propositional variables: SAS files/tasks name these generically
    #    (var0, var1, ...); the real semantics live in value_names.
    prop_var_names = [f"var{i}" for i in range(ir_task.sas_variables.num())]
    prop_domains = list(ir_task.sas_variables.value_names)

    # -- numeric variables: variable_names entries are fluent objects
    #    with a .symbol attribute (see IRTask.output(): nvar_obj.symbol).
    num_var_names = [nv.symbol for nv in ir_task.numeric_variables.variable_names]
    beta = resolve_beta(num_var_names, beta_by_name)

    # -- actions --
    actions = []
    for op in ir_task.operators:
        pre_p = list(op.prevail) + [(v, pre) for (v, pre, post, cond) in op.pre_post if pre != -1]
        eff_p = [(v, post) for (v, pre, post, cond) in op.pre_post]
        pre_n = [_ir_condition_to_constraint(c) for c in op.numeric_preconditions]

        eff_n = {}
        eff_assign = {}
        for target_var, expr in op.numeric_effects:
            kind, value = classify_effect(target_var, expr.coefficients, expr.constant, beta)
            (eff_n if kind == 'delta' else eff_assign)[target_var] = value

        actions.append(NumericAction(
            name=_strip_op_name_parens(op.name), pre_p=pre_p, pre_n=pre_n,
            eff_p=eff_p, eff_n=eff_n, eff_assign=eff_assign, cost=int(op.cost),
        ))

    # -- initial state --
    I_prop = list(ir_task.init.values)
    I_num = [int(v) for v in ir_task.init.num_values]

    # -- goal --
    G_prop = list(ir_task.sas_goal_pairs)
    G_num = [_ir_condition_to_constraint(c) for c in ir_task.numeric_goal_conditions]
    for c in G_num:
        if c.op != '==':
            raise NotImplementedError(
                "only equality numeric goals are supported by this translation"
            )

    return NumericTask(
        prop_var_names=prop_var_names, prop_domains=prop_domains,
        num_var_names=num_var_names, beta=beta, actions=actions,
        I_prop=I_prop, I_num=I_num, G_prop=G_prop, G_num=G_num, metric=True,
    )


def compile_ir_task(ir_task, beta_by_name: Dict[str, Tuple[int, int]]) -> "ClassicalSAS":
    """Single entry point for the in-memory path: IRTask + manual bounds
    -> classical SASTask. No file I/O involved."""
    task = ir_task_to_numeric_task(ir_task, beta_by_name)
    return to_sas_task(task)


# ---------------------------------------------------------------------
# T: Pi_n -> Pi_p 
# ---------------------------------------------------------------------

def relevant_vars(a: NumericAction) -> List[int]:
    """Variables that need enumeration during grounding: those appearing
    in a precondition, or updated by an additive-delta effect (their new
    value depends on the prior one). Pure constant-assignment effects
    (eff_assign) do NOT need enumeration here- the new value doesn't
    depend on what the variable was before, so no combinatorial blowup
    is needed for it, unless it's also separately read by a precondition."""
    s = set()
    for c in a.pre_n:
        s |= set(c.coeffs.keys())
    s |= set(a.eff_n.keys())
    return sorted(s)


def ground_action(a: NumericAction, beta: Dict[int, Tuple[int, int]], offset: int):
    """offset = number of propositional variables, so numeric var index x
    is placed at combined-space index (offset + x), never colliding with
    a propositional variable of the same raw index.

    product() over an empty range list yields exactly one empty combo,
    so an action with rel == [] (nothing to enumerate- e.g. no numeric
    preconditions and only constant-assignment effects, if any) still
    goes through this same loop exactly once, with iota == {}, with no
    special-casing needed."""
    rel = relevant_vars(a)
    ranges = [range(beta[x][0], beta[x][1] + 1) for x in rel]

    for combo in product(*ranges):
        iota = dict(zip(rel, combo))

        if not all(c.satisfied_by([iota.get(i, 0) for i in range(max(iota, default=-1) + 1)])
                   for c in a.pre_n):
            continue

        eff_num, ok = {}, True
        for x, delta in a.eff_n.items():
            new_val = iota[x] + delta
            l, u = beta[x]
            if not (l <= new_val <= u):
                ok = False
                break
            eff_num[x] = new_val
        if not ok:
            continue

        # Constant-assignment effects: the assigned value doesn't depend
        # on iota, so this check is identical on every iteration -- but
        # re-checking here keeps the function simple; cost is negligible.
        for x, const in a.eff_assign.items():
            l, u = beta[x]
            if not (l <= const <= u):
                raise ValueError(
                    f"action '{a.name}' assigns {const} to numeric var {x}, "
                    f"outside the supplied bound {beta[x]} -- the manual "
                    f"bound is too tight for this domain"
                )

        pre_p = list(a.pre_p) + [(offset + x, iota[x]) for x in rel]
        eff_p = (list(a.eff_p)
                 + [(offset + x, eff_num[x]) for x in rel if x in eff_num]
                 + [(offset + x, const) for x, const in a.eff_assign.items()])
        suffix = "_".join(f"n{x}={iota[x]}" for x in rel)
        gname = a.name + ("__" + suffix if suffix else "")
        yield (gname, pre_p, eff_p, a.cost)


def translate(task: NumericTask):
    """Returns (var_order_info, grounded_operators, init, goal) all indexed
    over a single combined variable space V_p ++ V_n."""
    n_prop = len(task.prop_var_names)
    n_num = len(task.num_var_names)
    combined_names = task.prop_var_names + task.num_var_names
    combined_domains = list(task.prop_domains) + [
        [str(k) for k in range(task.beta[i][0], task.beta[i][1] + 1)]
        for i in range(n_num)
    ]

    def num_var_idx(i):   # offset numeric var index into combined space
        return n_prop + i
    def num_val_idx(i, val):  # value -> local index within that var's domain
        return val - task.beta[i][0]

    # ground_action already places numeric-var entries at combined-space
    # index (n_prop + x) using raw integer values; here we just remap those
    # raw integer values to local (0-based) domain positions per variable.
    final_ops = []
    for a in task.actions:
        for name, pre_p, eff_p, cost in ground_action(a, task.beta, offset=n_prop):
            pre2, eff2 = [], []
            for v, val in pre_p:
                pre2.append((v, val) if v < n_prop else (v, num_val_idx(v - n_prop, val)))
            for v, val in eff_p:
                eff2.append((v, val) if v < n_prop else (v, num_val_idx(v - n_prop, val)))
            final_ops.append((name, pre2, eff2, cost))

    init = list(task.I_prop) + [num_val_idx(i, v) for i, v in enumerate(task.I_num)]

    goal = list(task.G_prop)
    for c in task.G_num:
        (x, k), = c.coeffs.items()
        assert k == 1
        goal.append((num_var_idx(x), num_val_idx(x, c.bound)))


    # Classical SAS+ requires every variable to have at least 2 possible
    # values (a size-1 variable carries no information); this drops any
    # such variable entirely, strips references to it from every
    # operator/init/goal, and reindexes the remaining variables densely.
    const_vars = {i for i, d in enumerate(combined_domains) if len(d) == 1}
    if const_vars:
        keep = [i for i in range(len(combined_domains)) if i not in const_vars]
        remap = {old: new for new, old in enumerate(keep)}

        combined_names = [combined_names[i] for i in keep]
        combined_domains = [combined_domains[i] for i in keep]
        init = [init[i] for i in keep]
        goal = [(remap[v], val) for v, val in goal if v not in const_vars]

        new_final_ops = []
        for name, pre_p, eff_p, cost in final_ops:
            pre2 = [(remap[v], val) for v, val in pre_p if v not in const_vars]
            eff2 = [(remap[v], val) for v, val in eff_p if v not in const_vars]
            new_final_ops.append((name, pre2, eff2, cost))
        final_ops = new_final_ops

    return combined_names, combined_domains, final_ops, init, goal


# ---------------------------------------------------------------------
# Emit as Fast Downward SASTask
# ---------------------------------------------------------------------

@dataclass
class ClassicalSAS:
    """Plain classic SAS+ (version 3) output — no numeric variables, no
    axioms, no comparison/numeric-axiom sections, metric as a single int.
    This is what a standard classical planner reads; it must NOT reuse the
    rich numeric-task SASTask format (that format is for numeric input,
    not classical output)."""
    var_names: List[str]
    domains: List[List[str]]
    operators: List[Tuple[str, List[Tuple[int, int]], List[Tuple[int, int, int, list]], int]]
    init: List[int]
    goal: List[Tuple[int, int]]
    use_metric: int = 0   # 0 = unit cost / ignore operator costs, 1 = use them

    def output(self, stream):
        print("begin_version", file=stream)
        print(3, file=stream)               #for reading
        print("end_version", file=stream)
        print("begin_metric", file=stream)
        print(self.use_metric, file=stream)
        print("end_metric", file=stream)
        print(len(self.var_names), file=stream)
        for i, name in enumerate(self.var_names):
            dom = self.domains[i]
            print("begin_variable", file=stream)
            print(f"var{i}", file=stream)
            print(-1, file=stream)
            print(len(dom), file=stream)
            for v in dom:
                print(f"Atom {name}={v}", file=stream)
            print("end_variable", file=stream)
        print(0, file=stream)  # mutex groups
        print("begin_state", file=stream)
        for v in self.init:
            print(v, file=stream)
        print("end_state", file=stream)
        print("begin_goal", file=stream)
        print(len(self.goal), file=stream)
        for var, val in sorted(self.goal):
            print(var, val, file=stream)
        print("end_goal", file=stream)
        print(len(self.operators), file=stream)
        for name, prevail, pre_post, cost in self.operators:
            print("begin_operator", file=stream)
            print(name, file=stream)
            print(len(prevail), file=stream)
            for var, val in sorted(prevail):
                print(var, val, file=stream)
            print(len(pre_post), file=stream)
            for var, pre, post, cond in pre_post:
                print(len(cond), end=' ', file=stream)
                for cvar, cval in cond:
                    print(cvar, cval, end=' ', file=stream)
                print(var, pre, post, file=stream)
            print(cost, file=stream)
            print("end_operator", file=stream)
        print(0, file=stream)  # axioms


def to_sas_task(task: NumericTask) -> ClassicalSAS:
    names, domains, ops, init, goal = translate(task)

    operators = []
    for name, pre, eff, cost in ops:
        eff_vars = {v for v, _ in eff}
        prevail = [(v, val) for v, val in pre if v not in eff_vars]
        pre_post = []
        pre_dict = dict(pre)
        for v, post in eff:
            pre_val = pre_dict.get(v, -1)
            pre_post.append((v, pre_val, post, []))
        operators.append((name, prevail, pre_post, cost))

    return ClassicalSAS(
        var_names=names, domains=domains, operators=operators,
        init=init, goal=sorted(goal), use_metric=0,
    )


def compile_ir_task(ir_task, beta_by_name: Dict[str, Tuple[int, int]]) -> ClassicalSAS:
    """Single entry point: IRTask + manual bounds -> classical SAS+ output.
    No file I/O involved. Call .output(stream) on the result yourself,
    e.g. inside the same 'with open(...) as output_file' block your
    driver already has."""
    task = ir_task_to_numeric_task(ir_task, beta_by_name)
    return to_sas_task(task)
