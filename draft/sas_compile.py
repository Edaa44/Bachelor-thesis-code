from __future__ import annotations

import itertools
import re
from dataclasses import replace
from typing import Dict, Iterable, List, Tuple, Optional

from .sas_model import (
    Fact,
    LinearExpression,
    SASAxiom,
    SASEffect,
    SASNumericCondition,
    SASNumericEffect,
    SASOperator,
    SASTask,
    SASVariable,
)
from .sas_parser import parse_sas, write_sas

Bounds = Dict[int, Tuple[int, int]]

class NumericSASCompiler:

    # input is a Numeric FD SAS task, cointains numeric variables, classical cannot 
    # search such a task directly. Every numeric variable => finite domain sas variable. 
    #
    """Compile Numeric Fast Downward-style SAS+ tasks to classical SAS+."""

    def compile_file(self, input_path: str, output_path: str) -> SASTask:
        #reads file, compiles and writes classical sas file. 
        task = parse_sas(input_path)
        compiled = self.compile_task(task)
        write_sas(compiled, output_path)
        return compiled

    def compile_task(self, task: SASTask) -> SASTask:
        return compile_sas_task(task)


def compile_numeric_sas(
    input_path: str,
    output_path: str,
) -> SASTask:
    return NumericSASCompiler().compile_file(input_path, output_path)


def compile_sas_task(task: SASTask) -> SASTask:
    #implements transformation
    if not task.numeric_variables:
        raise ValueError("input sas task has no numeric variables to compile")
    if task.numeric_axioms:
        raise ValueError(
            "this compiler does not support arithmetic numeric axioms"
            
        )
    bounds = _resolve_bounds(task) #first cheack bounds for all numeric variables, if not possible, raise error.
    encoded_var_for_numeric = _encoded_numeric_variables(task, bounds) 
    #mapping numeric variable id to the introduced classical sas, ex: x becomes num_x
    variables = list(task.variables) # start with original classical variables, then add encoded numeric variables.
    variables.extend(_make_encoded_variables(task, bounds))

    state = list(task.state)
    #preserve the classical initial state and append the encoded numeric initial values
    state.extend(_initial_numeric_values(task, bounds))

    condition_var_for_key: Dict[str, int] = {}
    #condition variable is true (value 0) exactly when the numeric comparison
    # holds for the current encoded numeric values
    condition_by_key: Dict[str, SASNumericCondition] = {}
    for condition in _all_numeric_conditions(task):
        key = _condition_key(condition)
        if key not in condition_var_for_key:
            condition_var_for_key[key] = len(variables)
            condition_by_key[key] = condition
            variables.append(_make_condition_variable(condition, len(condition_var_for_key)))
            state.append(1)

    #take existing classical axioms and add new axioms for numeric conditions and comparison axioms
    axioms = list(task.axioms)
    axioms.extend(_compile_comparison_axioms(task, bounds, encoded_var_for_numeric))
    axioms.extend(
        _compile_numeric_condition_axioms(
            condition_by_key,
            condition_var_for_key,
            bounds,
            encoded_var_for_numeric,
        )
    )

    #  compile every numeric operator into one or more ordinary SAS operators
    operators: List[SASOperator] = []
    for operator in task.operators:
        operators.extend(
            _compile_operator(
                operator,
                task,
                bounds,
                encoded_var_for_numeric,
                condition_var_for_key,
            )
        )

    # global constraint is represented as an ordinary goal, because comparison axioms 
    # now derive it from encoded numeric variables
    
    goal = list(task.goal)
    if task.global_constraint is not None and task.global_constraint not in goal:
        goal.append(task.global_constraint)
    for condition in task.numeric_goal:
        goal.append((condition_var_for_key[_condition_key(condition)], 0))

    return SASTask(
        version=task.version,
        metric=task.metric,
        variables=variables,
        numeric_variables=[],
        mutexes=list(task.mutexes),
        state=state,
        numeric_state=[],
        goal=sorted(goal),
        numeric_goal=[],
        operators=operators,
        axioms=axioms,
        comparison_axioms=[],
        numeric_axioms=[],
        global_constraint=None,
    )


def _resolve_bounds(task: SASTask) -> Bounds:
    # compiler needs finite domains to build the one-hot sas finite-domain encoding
    # initially each var is bounded only by its init value and then these bounds are expanded
    # using: min_/max_ numeric var, numeric goals/pre such as x == 0 and numeric effects: x:= x + 1
    bounds: Bounds = {}
    changed_numeric_vars = {
        effect.var for operator in task.operators for effect in operator.numeric_effects
    }

    for index, variable in enumerate(task.numeric_variables):
        initial = _require_int(task.numeric_state[index], variable.name)
        bounds[index] = (initial, initial)

    inferred = _infer_min_max_bounds(task, bounds) 
    inferred.update(_infer_bounds_from_expression_guards(task, bounds))
    bounds.update(inferred)

    missing = [ #check and throw error if somethign missing. 
        f"{index}:{task.numeric_variables[index].name}"
        for index in sorted(changed_numeric_vars)
        if bounds[index][0] == bounds[index][1]
    ]
    if missing: 
        raise ValueError(
            " The file must contain enough numeric min/max variables, goals, preconditions, "
            "  or guarded +/- effects to determine finite domains. Missing bounds for: "
            + ", ".join(missing)
        )

    return bounds


def _infer_min_max_bounds(task: SASTask, bounds: Bounds) -> Bounds:
    # if numeric values include a min/max, used as lower/upper bound for var 
    name_to_index = {
        _normalize_numeric_name(variable.name): index
        for index, variable in enumerate(task.numeric_variables)
    }
    values = {
        _normalize_numeric_name(variable.name): _require_int(task.numeric_state[index], variable.name)
        for index, variable in enumerate(task.numeric_variables)
    }
    inferred: Bounds = {}
    for name, index in name_to_index.items():
        min_name = f"min_{name}"
        max_name = f"max_{name}"
        if min_name in values and max_name in values:
            inferred[index] = (values[min_name], values[max_name])
    return inferred


def _encoded_numeric_variables(task: SASTask, bounds: Bounds) -> Dict[int, int]:
    # return the sas variable id assigned to each encoded numeric variable
    offset = len(task.variables)
    return {numeric_index: offset + i for i, numeric_index in enumerate(range(len(task.numeric_variables)))}


def _make_encoded_variables(task: SASTask, bounds: Bounds) -> List[SASVariable]:
    # create finite-domain sas variables for numeric variables, Ex: num variable with bounds [0,2]
    # num_x with values Atom num_x(0), Atom num_x(1), Atom num_x(2)
    variables: List[SASVariable] = []
    for index, numeric_variable in enumerate(task.numeric_variables):
        lo, hi = bounds[index]
        values = [
            f"Atom num_{safe_name(numeric_variable.name)}({value})"
            for value in range(lo, hi + 1)
        ]
        variables.append(SASVariable(f"num_{safe_name(numeric_variable.name)}", -1, values))
    return variables


def _initial_numeric_values(task: SASTask, bounds: Bounds) -> List[int]:
    # encode numeric initial values as finite-domain value indices
    values: List[int] = []
    for index, numeric_variable in enumerate(task.numeric_variables):
        initial = _require_int(task.numeric_state[index], numeric_variable.name)
        lo, hi = bounds[index]
        if not lo <= initial <= hi: #check logic and bounds 
            raise ValueError(f"Initial value {initial} for {numeric_variable.name} is outside bounds {lo}..{hi}")
        values.append(initial - lo)
    return values


def _compile_comparison_axioms(
    task: SASTask,
    bounds: Bounds,
    encoded_var_for_numeric: Dict[int, int],
) -> List[SASAxiom]:
    axioms: List[SASAxiom] = []
    # compile comparison axioms into ordinary SAS axioms, 
    # meaning: comparison variable is true iff numeric comparison holds for every satisfying assign. of the
    # encoded numeric variables
    for comparison in task.comparison_axioms:
        if len(comparison.parts) != 2:
            raise ValueError("Only binary numeric comparison axioms are supported")
        left, right = comparison.parts
        for left_value in _bound_values(bounds[left]):
            for right_value in _bound_values(bounds[right]):
                if compare(comparison.comparator, left_value, right_value):
                    axioms.append(
                        SASAxiom(
                            conditions=[
                                (encoded_var_for_numeric[left], _value_index(bounds[left], left_value)),
                                (encoded_var_for_numeric[right], _value_index(bounds[right], right_value)),
                            ],
                            effect=(comparison.effect_var, 0),
                        )
                    )
    return axioms


def _compile_operator(
    operator: SASOperator,
    task: SASTask,
    bounds: Bounds,
    encoded_var_for_numeric: Dict[int, int],
    condition_var_for_key: Dict[str, int],
) -> List[SASOperator]:
    #compile numeric operator into one or more ordinary SAS operators, by enumerating all possible transitions of the encoded numeric variables
    # an opartor has several effects, cartesian product. 
    numeric_preconditions = [
        (condition_var_for_key[_condition_key(condition)], 0)
        for condition in operator.numeric_conditions
    ]
    prevail = sorted(list(operator.prevail) + numeric_preconditions)

    if not operator.numeric_effects:
        return [replace(operator, prevail=prevail, numeric_conditions=[], numeric_effects=[])]

    for effect in operator.numeric_effects:
        if effect.conditions:
            raise ValueError(
                f"Conditional numeric effects are not supported {operator.name!r}"
            )

    transitions_per_effect = []
    for effect in operator.numeric_effects:
        transitions = _numeric_effect_transitions(effect, operator, task, bounds, encoded_var_for_numeric)
        if not transitions:
            print(f"Skipping operator {operator.name}: unsupported numeric effect outside increase/decrease scope")
            return []
        transitions_per_effect.append(transitions)

    compiled: List[SASOperator] = []
    for transition_tuple in itertools.product(*transitions_per_effect):
        suffix_parts = []
        effects = list(operator.effects)
        for numeric_effect, encoded_effect in transition_tuple:
            suffix_parts.append(
                f"{safe_name(task.numeric_variables[numeric_effect.var].name)}_"
                f"{encoded_effect.pre}_{encoded_effect.post}"
            )
            effects.append(encoded_effect)
        compiled.append(
            SASOperator(
                name=f"{operator.name}__{'__'.join(suffix_parts)}",
                prevail=prevail,
                effects=effects,
                numeric_conditions=[],
                numeric_effects=[],
                cost=operator.cost,
            )
        )
    return compiled


def _numeric_effect_transitions(
    effect: SASNumericEffect,
    operator: SASOperator,
    task: SASTask,
    bounds: Bounds,
    encoded_var_for_numeric: Dict[int, int],
) -> List[Tuple[SASNumericEffect, SASEffect]]:
    # return all in-bound classical transitions for one numeric effect
    amount = _effect_delta(effect, task, bounds)
    if amount is None:
        return []
    lo, hi = bounds[effect.var]
    transitions: List[Tuple[SASNumericEffect, SASEffect]] = []
    for old_value in _bound_values((lo, hi)):
        new_value = old_value + amount if effect.op == "+" else old_value - amount
        if effect.op == ":=":
            new_value = old_value + amount
        if not _numeric_conditions_allow(operator.numeric_conditions, effect.var, old_value, bounds):
            continue
        if lo <= new_value <= hi:
            transitions.append(
                (
                    effect,
                    SASEffect(
                        var=encoded_var_for_numeric[effect.var],
                        pre=_value_index((lo, hi), old_value),
                        post=_value_index((lo, hi), new_value),
                        conditions=[],
                    ),
                )
            )
    if not transitions:
        raise ValueError(
            f"Numeric effect on {task.numeric_variables[effect.var].name!r} has no in-bound transitions"
        )
    return transitions

    # iterate over all integer values in an inclusive bound interval
def _bound_values(bounds: Tuple[int, int]) -> Iterable[int]:
    return range(bounds[0], bounds[1] + 1)


def _value_index(bounds: Tuple[int, int], value: int) -> int:
    # If bounds are [3, 5], then value 3 has index 0, value 4 has index 1, etc
    return value - bounds[0]


def _require_int(value: float, name: str) -> int:
    # require a numeric value to be an integer
    if abs(value - int(value)) > 1e-9:
        raise ValueError(f"Numeric SAS value for {name!r} must be integer, got {value}")
    return int(value)


def _normalize_numeric_name(name: str) -> str:
    #normalize a numeric variable name for min/max
    cleaned = safe_name(name).lower()
    for prefix in ("pne_", "num_", "atom_"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    return cleaned


def _all_numeric_conditions(task: SASTask) -> List[SASNumericCondition]:
    #get numeric conditions from the task, including those in operators and the numeric goal
    conditions = list(task.numeric_goal)
    for operator in task.operators:
        conditions.extend(operator.numeric_conditions)
    return conditions


def _make_condition_variable(condition: SASNumericCondition, index: int) -> SASVariable:
    # create a derived SAS variable representing one numeric condition
    return SASVariable(
        f"num_condition_{index}",
        0,
        [
            f"Atom numeric-condition-{index}({_condition_key(condition)})",
            f"NegatedAtom numeric-condition-{index}({_condition_key(condition)})",
        ],
    )


def _compile_numeric_condition_axioms(
    condition_by_key: Dict[str, SASNumericCondition],
    condition_var_for_key: Dict[str, int],
    bounds: Bounds,
    encoded_var_for_numeric: Dict[int, int],
) -> List[SASAxiom]:
    #create classical sas axioms for numeric conditions, enumerate all value combinations of the numeric
    # variables occurring in the condition Whenever the condition is true, add an axiom
    axioms: List[SASAxiom] = []
    for key, condition in condition_by_key.items():
        variables = sorted(_expression_variables(condition.expression) | _expression_variables(condition.rhs))
        for assignment in _assignments_for_variables(variables, bounds):
            if _condition_holds(condition, assignment):
                axioms.append(
                    SASAxiom(
                        conditions=[
                            (encoded_var_for_numeric[var], _value_index(bounds[var], assignment[var]))
                            for var in variables
                        ],
                        effect=(condition_var_for_key[key], 0),
                    )
                )
    return axioms


def _assignments_for_variables(variables: List[int], bounds: Bounds) -> Iterable[Dict[int, int]]: 
    domains = [_bound_values(bounds[var]) for var in variables]
    for values in itertools.product(*domains):
        yield dict(zip(variables, values))


def _condition_holds(condition: SASNumericCondition, assignment: Dict[int, int]) -> bool:
    # evaluate a numeric condition under a concrete numeric assignment
    left = _eval_linear_expression(condition.expression, assignment)
    right = _eval_linear_expression(condition.rhs, assignment)
    return compare(condition.comparator, left, right)


def _numeric_conditions_allow(
    conditions: List[SASNumericCondition],
    changed_var: int,
    changed_value: int,
    bounds: Bounds,
) -> bool: #hceck if an old value can satisfy relevant numeric preconditions
    relevant = [
        condition for condition in conditions
        if changed_var in (_expression_variables(condition.expression) | _expression_variables(condition.rhs))
    ]
    if not relevant:
        return True
    other_vars = sorted(
        set().union(
            *[
                (_expression_variables(condition.expression) | _expression_variables(condition.rhs))
                for condition in relevant
            ]
        )
        - {changed_var}
    )
    for assignment in _assignments_for_variables(other_vars, bounds):
        assignment[changed_var] = changed_value
        if all(_condition_holds(condition, assignment) for condition in relevant):
            return True
    return False


def _effect_delta(
        # xtract the constant delta from a supported numeric effect
    effect: SASNumericEffect,
    task: SASTask,
    bounds: Bounds,
) -> Optional[int]:
    if effect.op in {"+", "-"} and effect.rhs_var is not None:
        amount_bounds = bounds[effect.rhs_var]
        if amount_bounds[0] != amount_bounds[1]:
            raise ValueError(
                f"Numeric effect amount variable {task.numeric_variables[effect.rhs_var].name!r} "
                "must be constant for finite compilation"
            )
        return amount_bounds[0]

    if effect.op == ":=" and effect.expression is not None:
        terms = dict(effect.expression.terms)
        coeff = terms.pop(effect.var, 0.0)
        if abs(coeff - 1.0) < 1e-9 and not terms:
            return _require_int(effect.expression.constant, task.numeric_variables[effect.var].name)
        # Constant assignments such as recharge are outside the thesis scope.
        return None

    return None


def _infer_bounds_from_expression_guards(task: SASTask, bounds: Bounds) -> Bounds:
    # Infer bounds from normalized numeric conditions and guarded effects.
    inferred = dict(bounds)
    for var, value in enumerate(task.numeric_state):
        initial = _require_int(value, task.numeric_variables[var].name)
        lo, hi = inferred.get(var, (initial, initial))
        inferred[var] = (min(lo, initial), max(hi, initial))

    for operator in task.operators:
        for condition in operator.numeric_conditions + task.numeric_goal:
            single = _single_variable_bound(condition)
            if single is None:
                continue
            var, lower, upper = single
            lo, hi = inferred.get(var, bounds.get(var, (0, 0)))
            if lower is not None:
                lo = min(lo, lower)
                hi = max(hi, lower)
            if upper is not None:
                lo = min(lo, upper)
                hi = max(hi, upper)
            inferred[var] = (lo, hi)

        for effect in operator.numeric_effects:
            delta = _effect_delta(effect, task, inferred)
            if delta is None:
                continue
            lo, hi = inferred.get(effect.var, bounds.get(effect.var, (0, 0)))
            for condition in operator.numeric_conditions:
                single = _single_variable_bound(condition)
                if single is None or single[0] != effect.var:
                    continue
                _var, lower, upper = single
                if lower is not None:
                    lo = min(lo, lower + delta)
                    hi = max(hi, lower + delta)
                if upper is not None:
                    lo = min(lo, upper + delta)
                    hi = max(hi, upper + delta)
            inferred[effect.var] = (lo, hi)
    return inferred


def _single_variable_bound(condition: SASNumericCondition) -> Optional[Tuple[int, Optional[int], Optional[int]]]:
    # extract a simple bound from a single-variable linear condition
    expr = _subtract_expressions(condition.expression, condition.rhs)
    if len(expr.terms) != 1:
        return None
    (var, coeff), = expr.terms.items()
    if abs(abs(coeff) - 1.0) > 1e-9:
        return None
    # coeff * x + c comparator 0
    threshold = -expr.constant / coeff
    if abs(threshold - int(threshold)) > 1e-9:
        return None
    value = int(threshold)
    comparator = condition.comparator
    if coeff < 0:
        comparator = _reverse_comparator(comparator)
    if comparator == "=":
        return var, value, value
    if comparator == ">=":
        return var, value, None
    if comparator == ">":
        return var, value + 1, None
    if comparator == "<=":
        return var, None, value
    if comparator == "<":
        return var, None, value - 1
    return None


def _subtract_expressions(left: LinearExpression, right: LinearExpression) -> LinearExpression:
    # Return left - right as a normalized LinearExpression
    result = LinearExpression(dict(left.terms), left.constant - right.constant)
    for var, coeff in right.terms.items():
        result.terms[var] = result.terms.get(var, 0.0) - coeff
    result.terms = {var: coeff for var, coeff in result.terms.items() if abs(coeff) > 1e-9}
    return result


def _reverse_comparator(comparator: str) -> str: # reverse a comparator when multiplying a condition by
    return {
        ">=": "<=",
        "<=": ">=",
        ">": "<",
        "<": ">",
        "=": "=",
        "!=": "!=",
    }[comparator]


def _expression_variables(expression: LinearExpression) -> set[int]: #Return numeric variable ids used by a linear expression
    return set(expression.terms)


def _eval_linear_expression(expression: LinearExpression, assignment: Dict[int, int]) -> float:
    return expression.constant + sum(coeff * assignment[var] for var, coeff in expression.terms.items())


def _condition_key(condition: SASNumericCondition) -> str:
    return safe_name(
        f"{_expression_key(condition.expression)}_{condition.comparator}_{_expression_key(condition.rhs)}"
    )


def _expression_key(expression: LinearExpression) -> str:
    parts = [f"{coeff:g}x{var}" for var, coeff in sorted(expression.terms.items())]
    if abs(expression.constant) > 1e-9 or not parts:
        parts.append(f"{expression.constant:g}")
    return "_plus_".join(parts)


def compare(op: str, left: float, right: float) -> bool:
    if op in {"=", "=="}:
        return abs(left - right) < 1e-9
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == "!=":
        return abs(left - right) >= 1e-9
    raise ValueError(f"Unsupported comparison operator {op}")


def safe_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", name)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or "x"

