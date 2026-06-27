from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# data type specializations for the sas model and how its represented ( and used, 
# and "edited"))
Fact = Tuple[int, int]


@dataclass
class SASVariable:
    name: str  # name printed in the file, for ex var0 or num_x
    axiom_layer: int # -1 means this is a normal state variable
    values: List[str] # example: values[0] = Atom visited(x0y0z0)


@dataclass
class SASNumericVariable:
    name: str
    axiom_layer: int #numeric variables usually have -1
    type_name: str #R,C,D,I which type 


@dataclass
class SASEffect:
    var: int #domain variable affected by the effect
    pre: int #precondition value
    post: int 
    conditions: List[Fact] = field(default_factory=list) # numeric conditional effects are intentionally not supported


@dataclass
class LinearExpression:
     # Mapping from numeric variable id to coefficient.
     # sum(coeff_i * numeric_var_i) + constant means 1 * numeric_variable_0 - 1
    terms: Dict[int, float] = field(default_factory=dict)
    constant: float = 0.0 #te constant used above


@dataclass
class SASNumericCondition:
    #rhs is usually the zero expression, expressions compared against zero
    expression: LinearExpression # left
    comparator: str #comparator
    rhs: LinearExpression #right hand side


@dataclass
class SASNumericEffect:
    # assignment-to-constant effects like recharge is skipped
    # form  x := x + c
    var: int #affected var
    op: str #operator
    rhs_var: Optional[int] = None #right hand side variable
    expression: Optional[LinearExpression] = None #
    conditions: List[Fact] = field(default_factory=list)


@dataclass
class SASOperator:
    name: str
    prevail: List[Fact] #list of preconditions 
    effects: List[SASEffect] #list of effects 
    numeric_conditions: List[SASNumericCondition] #list of numeric conditions
    numeric_effects: List[SASNumericEffect] #list of numeric effects
    cost: str #cost of action


@dataclass
class SASAxiom:
    #t hey tell the planner that if some conditions hold, then a derived fact becomes true,
    conditions: List[Fact] # what must hold for the axiom to derive its effect
    effect: Fact # the effect of it


@dataclass
class SASComparisonAxiom:
    # a comparison axiom says that a propositional variable is true
    # exactly when a comparison between numeric variables holds
    effect_var: int #var
    comparator: str #operator
    parts: List[int]


@dataclass
class SASNumericAxiom:
    # numeric axioms define derived numeric variables from other numeric
    # variables, for example:

    #d := a + b
    #d := a - b
    effect_var: int #variable affected
    op: str #operator
    parts: List[int]

# structure of task 
@dataclass
class SASTask:
    #the numeric variables are still stored, after compilation,
    # those numeric fields are empty because all numeric information has been
    # compiled into ordinary finite-domain SAS variables
    version: Optional[int]
    metric: List[str]
    variables: List[SASVariable]
    numeric_variables: List[SASNumericVariable]
    mutexes: List[List[Fact]]
    state: List[int]
    numeric_state: List[float]
    goal: List[Fact]
    numeric_goal: List[SASNumericCondition]
    operators: List[SASOperator]
    axioms: List[SASAxiom]
    comparison_axioms: List[SASComparisonAxiom]
    numeric_axioms: List[SASNumericAxiom]
    global_constraint: Optional[Fact] = None

