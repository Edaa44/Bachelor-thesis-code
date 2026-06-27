from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

from .sas_model import (
    Fact,
    LinearExpression,
    SASAxiom,
    SASComparisonAxiom,
    SASEffect,
    SASNumericCondition,
    SASNumericAxiom,
    SASNumericEffect,
    SASNumericVariable,
    SASOperator,
    SASTask,
    SASVariable,
)

# helper class to read files
class _LineReader:
    def __init__(self, lines: Sequence[str]):
        self.lines = [line.strip() for line in lines if line.strip()]
        self.pos = 0

    def peek(self, offset: int = 0) -> Optional[str]: # to inspect upcoming lines without consuming them
        index = self.pos + offset
        return self.lines[index] if index < len(self.lines) else None

    def read(self, expected: Optional[str] = None) -> str: #to consume a line, optionally checking that it is what we expected
        if self.pos >= len(self.lines): #check 
            raise ValueError("Unexpected end of SAS file") #throw if we are out, or file is cut
        line = self.lines[self.pos]
        if expected is not None and line != expected: #throw error if not expected
            raise ValueError(f"Expected {expected!r}, got {line!r} at line {self.pos + 1}")
        self.pos += 1 
        return line

    def read_int(self) -> int: #for counting the lines
        return int(self.read())


def parse_sas(path: str) -> SASTask:
    #parse sas task from file, returns a SASTask object
    # object is still numeric if the file
    # contained numeric sections 
    # the compiler later turns it into a classical task
    reader = _LineReader(Path(path).read_text().splitlines())

    #peek at the first line to see if it is a version line, if so, read it (consume it) and store the version number, otherwise none
    #version and metric are optional, if they are not present, we use default values, just adapted to the output.sas file

    version: Optional[int] = None
    if reader.peek() == "begin_version":
        reader.read("begin_version")
        version = reader.read_int()
        reader.read("end_version")

    metric: List[str] = ["0"]
    if reader.peek() == "begin_metric":
        reader.read("begin_metric")
        metric = reader.read().split()
        reader.read("end_metric")

    #ordinary variables come first
    variables = _parse_variables(reader)
    numeric_variables: List[SASNumericVariable] = []
    numeric_count_or_mutex_count = reader.read_int()
    if reader.peek() == "begin_numeric_variables": #just a check for both cases
        numeric_variables = _parse_numeric_variables(reader, numeric_count_or_mutex_count)
        mutex_count = reader.read_int()
    elif reader.peek() == "begin_numeric_variable":
        numeric_variables = _parse_numeric_variable_blocks(reader, numeric_count_or_mutex_count)
        mutex_count = reader.read_int()
    else:
        mutex_count = numeric_count_or_mutex_count

    #mutex groups, facts in one group cannot be true together
    mutexes = [_parse_mutex(reader) for _ in range(mutex_count)]
    #propositional states and numeric are separate, also read separately
    state = _parse_state(reader)
    numeric_state: List[float] = []
    if reader.peek() == "begin_numeric_state":
        numeric_state = _parse_numeric_state(reader)
    #separation also counts for goal
    goal = _parse_goal(reader)
    numeric_goal: List[SASNumericCondition] = []
    if reader.peek() == "begin_numeric_goal":
        numeric_goal = _parse_numeric_goal(reader)

    operators = [_parse_operator(reader, has_numeric=bool(numeric_variables)) for _ in range(reader.read_int())]
    # ordinary axioms
    axioms = [_parse_axiom(reader) for _ in range(reader.read_int())]

    
    comparison_axioms: List[SASComparisonAxiom] = []
    numeric_axioms: List[SASNumericAxiom] = []
    global_constraint: Optional[Fact] = None

    #peek and read the comparison axioms
    if reader.peek() is not None:
        comparison_count = reader.read_int()
        if reader.peek() == "begin_comparison_axioms":
            reader.read("begin_comparison_axioms")
            comparison_axioms = [_parse_comparison_axiom(reader) for _ in range(comparison_count)]
            reader.read("end_comparison_axioms")
        else: #throw error if not found
            raise ValueError("Expected begin_comparison_axioms after comparison axiom count")

    #peek and read the numeric comparison axioms
    if reader.peek() is not None:
        numeric_axiom_count = reader.read_int()
        if reader.peek() == "begin_numeric_axioms":
            reader.read("begin_numeric_axioms")
            numeric_axioms = [_parse_numeric_axiom(reader) for _ in range(numeric_axiom_count)]
            reader.read("end_numeric_axioms")
        else: #throw error if not found
            raise ValueError("Expected begin_numeric_axioms after numeric axiom count")

    if reader.peek() == "begin_global_constraint":
        reader.read("begin_global_constraint")
        global_constraint = _parse_fact(reader.read())
        reader.read("end_global_constraint")

    if reader.peek() is not None: #throw error if more given that needed in the sas file
        raise ValueError(f"Unexpected trailing SAS content: {reader.peek()!r}")

    #after reading the file, we return a SASTask object with all the parsed data
    return SASTask(
        version=version,
        metric=metric,
        variables=variables,
        numeric_variables=numeric_variables,
        mutexes=mutexes,
        state=state,
        numeric_state=numeric_state,
        goal=goal,
        numeric_goal=numeric_goal,
        operators=operators,
        axioms=axioms,
        comparison_axioms=comparison_axioms,
        numeric_axioms=numeric_axioms,
        global_constraint=global_constraint,
    )

#This is called after all numeric contents have been compiled away. we dont begin with `begin_numeric_goal` or smth, output is classical sas structure
def write_sas(task: SASTask, path: str) -> None:
    lines: List[str] = []
    lines.extend(["begin_version", str(task.version if task.version is not None else 3), "end_version"])
    lines.extend(["begin_metric", _classical_metric_line(task.metric), "end_metric"])

    lines.append(str(len(task.variables)))
    for variable in task.variables:
        lines.extend(["begin_variable", variable.name, str(variable.axiom_layer), str(len(variable.values))])
        lines.extend(variable.values)
        lines.append("end_variable")

    lines.append(str(len(task.mutexes)))
    for mutex in task.mutexes:
        lines.extend(["begin_mutex_group", str(len(mutex))])
        lines.extend(f"{var} {val}" for var, val in mutex)
        lines.append("end_mutex_group")

    lines.append("begin_state")
    lines.extend(str(value) for value in task.state)
    lines.append("end_state")

    lines.extend(["begin_goal", str(len(task.goal))])
    lines.extend(f"{var} {val}" for var, val in task.goal)
    lines.append("end_goal")

    lines.append(str(len(task.operators)))
    for operator in task.operators:
        lines.extend(["begin_operator", operator.name, str(len(operator.prevail))])
        lines.extend(f"{var} {val}" for var, val in operator.prevail)
        lines.append(str(len(operator.effects)))
        for effect in operator.effects:
            cond = " ".join(f"{var} {val}" for var, val in effect.conditions)
            prefix = f"{len(effect.conditions)}{(' ' + cond) if cond else ''}"
            lines.append(f"{prefix} {effect.var} {effect.pre} {effect.post}")
        lines.extend([str(operator.cost), "end_operator"])

    lines.append(str(len(task.axioms)))
    for axiom in task.axioms:
        lines.extend(["begin_rule", str(len(axiom.conditions))])
        lines.extend(f"{var} {val}" for var, val in axiom.conditions)
        var, value = axiom.effect
        lines.extend([f"{var} {1 - value} {value}", "end_rule"])

    Path(path).write_text("\n".join(lines) + "\n")

#parse the ordinary finite-domain sas variable section, each part of variable is read and consumed
def _parse_variables(reader: _LineReader) -> List[SASVariable]:
    variables: List[SASVariable] = []
    for _ in range(reader.read_int()):
        reader.read("begin_variable")
        name = reader.read()
        axiom_layer = reader.read_int()
        value_count = reader.read_int()
        values = [reader.read() for _ in range(value_count)]
        reader.read("end_variable")
        variables.append(SASVariable(name, axiom_layer, values))
    return variables


def _parse_numeric_variables(reader: _LineReader, count: int) -> List[SASNumericVariable]:
    variables: List[SASNumericVariable] = []
    reader.read("begin_numeric_variables")
    for _ in range(count):
        parts = reader.read().split()
        if len(parts) < 3:
            raise ValueError("Numeric variable line must contain type, axiom layer, and name")
        variables.append(SASNumericVariable(" ".join(parts[2:]), int(parts[1]), parts[0]))
    reader.read("end_numeric_variables")
    return variables

# parse the project format with one block per numeric variable
def _parse_numeric_variable_blocks(reader: _LineReader, count: int) -> List[SASNumericVariable]:
    variables: List[SASNumericVariable] = []
    for _ in range(count):
        reader.read("begin_numeric_variable")
        name = reader.read()
        axiom_layer = reader.read_int()
        reader.read("end_numeric_variable")
        variables.append(SASNumericVariable(name, axiom_layer, "regular"))
    return variables


def _parse_mutex(reader: _LineReader) -> List[Fact]:
    #parse mutex group
    reader.read("begin_mutex_group")
    facts = [_parse_fact(reader.read()) for _ in range(reader.read_int())]
    reader.read("end_mutex_group")
    return facts


def _parse_state(reader: _LineReader) -> List[int]:
    reader.read("begin_state")
    values: List[int] = []
    while reader.peek() != "end_state":
        values.append(reader.read_int())
    reader.read("end_state")
    return values

#parse the init values, the i-th number is the init value of the i-th numeric variable. 
def _parse_numeric_state(reader: _LineReader) -> List[float]:
    reader.read("begin_numeric_state")
    values: List[float] = []
    while reader.peek() != "end_numeric_state":
        values.append(float(reader.read()))
    reader.read("end_numeric_state")
    return values

#parse ordinary goals and numeric goal separate each
def _parse_goal(reader: _LineReader) -> List[Fact]:
    reader.read("begin_goal")
    facts = [_parse_fact(reader.read()) for _ in range(reader.read_int())]
    reader.read("end_goal")
    return facts


def _parse_numeric_goal(reader: _LineReader) -> List[SASNumericCondition]:
    reader.read("begin_numeric_goal")
    conditions = [_parse_numeric_condition(reader.read()) for _ in range(reader.read_int())]
    reader.read("end_numeric_goal")
    return conditions

#parse one grounded SAS operator
def _parse_operator(reader: _LineReader, has_numeric: bool) -> SASOperator:
    reader.read("begin_operator")
    name = reader.read()
    prevail = [_parse_fact(reader.read()) for _ in range(reader.read_int())]
    effects: List[SASEffect] = []
    for _ in range(reader.read_int()):
        parts = [int(part) for part in reader.read().split()]
        cond_count = parts[0]
        cond_parts = parts[1:1 + 2 * cond_count]
        rest = parts[1 + 2 * cond_count:]
        if len(rest) != 3:
            raise ValueError("SAS effect line must end with var pre post")
        effects.append(SASEffect(rest[0], rest[1], rest[2], _pairs(cond_parts)))

    numeric_conditions: List[SASNumericCondition] = []
    numeric_effects: List[SASNumericEffect] = []
    if has_numeric:
        numeric_count = reader.read_int()
        if numeric_count and _looks_like_numeric_condition(reader.peek() or ""):
            numeric_conditions = [_parse_numeric_condition(reader.read()) for _ in range(numeric_count)]
            numeric_effects = [_parse_expression_numeric_effect(reader.read()) for _ in range(reader.read_int())]
        else:
            for _ in range(numeric_count):
                parts = reader.read().split()
                cond_count = int(parts[0])
                cond_parts = [int(part) for part in parts[1:1 + 2 * cond_count]]
                rest = parts[1 + 2 * cond_count:]
                if len(rest) != 3:
                    raise ValueError("Numeric effect line must end with nvar op rhs_nvar")
                numeric_effects.append(
                    SASNumericEffect(int(rest[0]), rest[1], int(rest[2]), None, _pairs(cond_parts))
                )

    cost = reader.read()
    reader.read("end_operator")
    return SASOperator(name, prevail, effects, numeric_conditions, numeric_effects, cost)

# parse one ordinary SAS axiom/rule, SAS prints an axiom effect as `var old new`
def _parse_axiom(reader: _LineReader) -> SASAxiom:
    reader.read("begin_rule")
    conditions = [_parse_fact(reader.read()) for _ in range(reader.read_int())]
    var, _old, new = [int(part) for part in reader.read().split()]
    reader.read("end_rule")
    return SASAxiom(conditions, (var, new))


def _parse_comparison_axiom(reader: _LineReader) -> SASComparisonAxiom:
    parts = reader.read().split()
    if len(parts) < 4:
        raise ValueError("Comparison axiom line must contain effect, comparator, and parts")
    return SASComparisonAxiom(int(parts[0]), parts[1], [int(part) for part in parts[2:]])


def _parse_numeric_axiom(reader: _LineReader) -> SASNumericAxiom:
    parts = reader.read().split()
    if len(parts) < 4:
        raise ValueError("Numeric axiom line must contain effect, operator, and parts")
    return SASNumericAxiom(int(parts[0]), parts[1], [int(part) for part in parts[2:]])


def _parse_fact(line: str) -> Fact:
    var, val = [int(part) for part in line.split()]
    return var, val


def _pairs(values: List[int]) -> List[Fact]:
    if len(values) % 2 != 0:
        raise ValueError(f"Expected an even number of fact entries, got {values}")
    return [(values[i], values[i + 1]) for i in range(0, len(values), 2)]

# parser keeps the two sides explicit as expression comparator rhs
def _parse_numeric_condition(line: str) -> SASNumericCondition:
    for comparator in ("==", ">=", "<=", "!=", ">", "<"):
        marker = f" {comparator} "
        if marker in line:
            lhs, rhs = line.split(marker, 1)
            return SASNumericCondition(
                _parse_linear_expression(lhs),
                "=" if comparator == "==" else comparator,
                _parse_linear_expression(rhs),
            )
    raise ValueError(f"Could not parse numeric condition: {line!r}")

# expression-style numeric effect
def _parse_expression_numeric_effect(line: str) -> SASNumericEffect:
    if ":=" not in line:
        raise ValueError(f"Could not parse numeric effect: {line!r}")
    target, expression = line.split(":=", 1)
    return SASNumericEffect(int(target.strip()), ":=", None, _parse_linear_expression(expression), [])


def _parse_linear_expression(text: str) -> LinearExpression:
    #Ex:
    #+ 1*0 +  - 1.0  ->  1 * var0 - 1
    # - 1*3           -> -1 * var3
    # + 9.0           ->  constant 9 assignmenths not supported in thesis. 

    tokens = text.replace("+", " + ").replace("-", " - ").split()
    sign = 1.0
    expression = LinearExpression()
    for token in tokens:
        if token == "+":
            sign = 1.0
            continue
        if token == "-":
            sign = -1.0
            continue
        if "*" in token:
            coeff_text, var_text = token.split("*", 1)
            coeff = sign * float(coeff_text)
            var = int(var_text)
            expression.terms[var] = expression.terms.get(var, 0.0) + coeff
        else:
            expression.constant += sign * float(token)
        sign = 1.0
    expression.terms = {
        var: coeff for var, coeff in expression.terms.items() if abs(coeff) > 1e-9
    }
    return expression


def _looks_like_numeric_condition(line: str) -> bool:
    return any(f" {comparator} " in line for comparator in ("==", ">=", "<=", "!=", ">", "<"))


def _classical_metric_line(metric: List[str]) -> str:
    if len(metric) == 1:
        return metric[0]
    # Numeric Fast Downward prints e.g. "< -1".  Classical Fast Downward uses
    # 0/1 here; the compiled task currently preserves operator costs but not a
    # numeric metric expression, so unit-cost mode is the safe default.
    return "0"

