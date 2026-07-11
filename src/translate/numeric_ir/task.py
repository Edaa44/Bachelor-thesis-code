from numeric_ir.semantics import PropositionalAxiomSemanticsExtractor, NumericAxiomSemanticsExtractor
from numeric_ir.linear_expr import LinearCondition, LinearExpression
from sas_tasks import SASInit, SASNumericVariables, SASTask, SASVariables, SASOperator
from typing import Tuple, List, Dict

class NumericGoal:
    def __init__(self, numeric_goals):
        self.numeric_goals = numeric_goals

    def add_goal(self, var_id, condition, value):
        self.numeric_goals.append((var_id, condition, value))

    def output(self, stream):
        print(len(self.numeric_goals), file=stream)
        for var_id, condition, value in self.numeric_goals:
            print(f"{var_id} {condition} {value}", file=stream)

class NumericOperator:
    def __init__(
            self,
            name: str,
            prevail: list[tuple[int, int]],
            pre_post: list[tuple[int, int, int, tuple]],
            numeric_preconditions: list[LinearCondition],
            numeric_effects: list[tuple[int, LinearExpression]],
            cost: int):
        self.name = name
        self.prevail = prevail
        self.pre_post = pre_post
        self.numeric_preconditions = numeric_preconditions
        self.numeric_effects = numeric_effects
        self.cost = cost

def rename_numeric_condition(linear_condition, numeric_var_mapping):
    mapped_expr = rename_numeric_expression(linear_condition.expr, numeric_var_mapping)
    return LinearCondition(mapped_expr, linear_condition.comp)


def rename_numeric_expression(linear_expression, numeric_var_mapping):
    def map_var(var_id):
        assert var_id in numeric_var_mapping, f"Expression variable {var_id} not found in numeric variable mapping."
        return numeric_var_mapping[var_id]

    mapped_coeffs = {map_var(v): c for v, c in linear_expression.coefficients.items()}
    mapped_expr = LinearExpression(mapped_coeffs, linear_expression.constant)
    return mapped_expr


class IRTask:
    """Integer-restricted view over a SAS task with extracted numeric semantics."""

    def __init__(self, sas_task_instance: SASTask):
        assert isinstance(sas_task_instance, SASTask)
        self.sas_task: SASTask = sas_task_instance

        self.semantics = NumericAxiomSemanticsExtractor(self.sas_task)

        self.propositional_semantics = PropositionalAxiomSemanticsExtractor(self.sas_task)
        self.propositional_derived_variables = {var_id for var_id, _ in self.propositional_semantics.propositional_semantic}

        self.metric_direction, self.metric_var_id = self.sas_task.metric

        self.sas_variables, self.sas_variable_mapping = (
            self._get_relevant_sas_variables()
        )
        self.numeric_variables, self.numeric_variable_mapping = (
            self._get_relevant_numeric_variables()
        )
        self.init = self.get_relevant_init(
            self.sas_variable_mapping,
            self.numeric_variable_mapping,
        )

        self.sas_goal_pairs, self.numeric_goal_conditions = self.get_relevant_goal(
            self.sas_variable_mapping,
            self.numeric_variable_mapping,
        )

        self.operators = self._get_operators()

    def _expand_propositional_fact(
        self,
        fact: PropositionalAxiomSemanticsExtractor.Fact,
    ) -> PropositionalAxiomSemanticsExtractor.Conjunction:
        # Fact contains a derived propositional variable: expand its semantics
        if fact in self.propositional_semantics.propositional_semantic:
            return self.propositional_semantics.propositional_semantic[fact]
    
        # Fact contains a derived propositional variable that for some unknown reason was not expanded
        var_id, _value = fact
        if var_id in self.propositional_derived_variables:
            raise ValueError(
                "Unsupported unresolved derived propositional fact %s" % (fact,)
            )
    
        # Fact contains a derived comparison proxy: return
        return (fact,)

    #def _collect_operator_conditions(self, op):
    #    conditions = []
    #    conditions.extend(op.prevail)
    #    for var, pre, _post, _cond in op.pre_post:
    #        if pre != -1:
    #            conditions.append((var, pre))
    #    return conditions

    def _atom_to_linear_condition(
        self,
        atom: Tuple[int, int],
    ) -> LinearCondition | None:
        var_id, value = atom
        if var_id not in self.semantics.compare_semantics:
            return None
        
        linear_condition = self.semantics.compare_semantics[var_id]
        assert value in (0, 1), f"Condition value {value} is not binary."
        if value == 1:
            linear_condition = linear_condition.negate()
        return linear_condition

    def _append_goal_fact(
        self,
        fact: PropositionalAxiomSemanticsExtractor.Fact,
        sas_goal: list[tuple[int, int]],
        numeric_goals: list[LinearCondition],
        sas_var_mapping: dict[int, int],
        numeric_var_mapping: dict[int, int],
    ):
        numeric_condition = self._atom_to_linear_condition(fact)
        if numeric_condition is not None:
            renamed_numeric_condition = rename_numeric_condition(numeric_condition, numeric_var_mapping)
            numeric_goals.append(renamed_numeric_condition)
            return

        var_id, value = fact
        if var_id in sas_var_mapping:
            sas_goal.append((sas_var_mapping[var_id], value))
            return

        raise ValueError("Unsupported goal fact %s" % (fact,))

    def _unpack_goal_axioms(self) -> list[PropositionalAxiomSemanticsExtractor.Fact]:
        goal_facts = []
        for fact in self.sas_task.goal.pairs:
            goal_facts.extend(self._expand_propositional_fact(fact))
        return goal_facts
        #goal_facts = list(self.sas_task.goal.pairs)
        #while True:
        #    expanded_any = False
        #    next_goal_facts = []
        #    for fact in goal_facts:
        #        matching_axioms = [
        #            axiom for axiom in self.sas_task.axioms if axiom.effect == fact
        #        ]
        #        if len(matching_axioms) == 1:
        #            assert(False) # Does this ever happen?
        #            next_goal_facts.extend(matching_axioms[0].condition)
        #            expanded_any = True
        #        elif len(matching_axioms) > 1:
        #            raise ValueError(
        #                "Cannot unpack disjunctive goal axiom for fact %s" % (fact,)
        #            )
        #        else:
        #            next_goal_facts.append(fact)
        #    if not expanded_any:
        #        return next_goal_facts
        #    goal_facts = next_goal_facts

    def _uses_metric_variable_cost(self):
        return self.metric_direction == "<" and self.metric_var_id != -1

    def _is_metric_variable(self, var_id):
        return self._uses_metric_variable_cost() and var_id == self.metric_var_id

    def _extract_metric_effect_cost(self, op):
        metric_effects = [
            effect for effect in op.assign_effects if effect[0] == self.metric_var_id
        ]
        if not metric_effects:
            return 0
        if len(metric_effects) != 1:
            raise ValueError(
                "Unsupported multiple effects on metric variable %s in operator %s"
                % (self.metric_var_id, op.name)
            )

        nvar, ass_op, ass_var, cond = metric_effects[0]
        assert nvar == self.metric_var_id
        if cond:
            raise ValueError(
                "Unsupported conditional effect on metric variable %s in operator %s"
                % (self.metric_var_id, op.name)
            )
        if ass_op != "+":
            raise ValueError(
                "Unsupported non-additive effect %s on metric variable %s in operator %s"
                % (ass_op, self.metric_var_id, op.name)
            )
        if self.sas_task.numeric_variables.types[ass_var] != "C":
            raise ValueError(
                "Unsupported non-constant additive effect on metric variable %s in operator %s"
                % (self.metric_var_id, op.name)
            )

        linex = self.semantics.numeric_semantics[ass_var]
        assert not linex.coefficients
        const = linex.constant
        if const is None:
            raise ValueError(
                "Unsupported non-integer additive effect on metric variable %s in operator %s"
                % (self.metric_var_id, op.name)
            )
        return int(const)

    def _get_operator_cost(self, op):
        if not self._uses_metric_variable_cost():
            return int(op.cost)
        return self._extract_metric_effect_cost(op)

    def _is_comparison_proxy_variable(self, value_names):
        if not value_names or value_names[-1] != "<none of those>":
            return False
        comparison_prefixes = ("<", "<=", ">", ">=", "=", "!=")
        return all(
            isinstance(value_name, str) and value_name.startswith(comparison_prefixes)
            for value_name in value_names[:-1]
        )

    def _get_relevant_sas_variables(self):
        sas_variables = self.sas_task.variables
        relevant_ranges = []
        relevant_axiom_layers = []
        relevant_value_names = []
        var_mapping = {}
        for var_id in range(sas_variables.num()):
            # Exclude numeric comparison proxies
            if var_id in self.semantics.compare_semantics:
                continue
            # Exclude derived propositional variables
            if var_id in self.propositional_derived_variables:
                continue
            # Catch unresolved internal auxiliary axiom variables (new-axiom@*)
            vals = sas_variables.value_names[var_id]
            if any(("new-axiom@" in str(v)) for v in vals):
                assert(False), "Internal auxiliary axiom variable found"
                continue
            # Exclude any remaining unresolved comparison proxy variables.
            if self._is_comparison_proxy_variable(vals):
                assert(False), "Unresolved comparison proxy variable found"
                continue
            var_mapping[var_id] = len(relevant_ranges)
            relevant_ranges.append(sas_variables.ranges[var_id])
            relevant_axiom_layers.append(sas_variables.axiom_layers[var_id])
            relevant_value_names.append(sas_variables.value_names[var_id])
        return (
            SASVariables(
                relevant_ranges,
                relevant_axiom_layers,
                relevant_value_names,
                -1,
            ),
            var_mapping,
        )

    #def _is_cost_variable(self, numeric_var):
    #    return getattr(numeric_var, "symbol", "") == "PNE cost()"

    def _get_relevant_numeric_variables(self):
        sas_numeric_variables = self.sas_task.numeric_variables
        relevant_variable_names = []
        relevant_axiom_layers = []
        relevant_types = []
        var_mapping = {}
        for var_id in range(sas_numeric_variables.num()):
            var_name = sas_numeric_variables.variable_names[var_id]
            var_axiom_layer = sas_numeric_variables.axiom_layers[var_id]
            var_type = sas_numeric_variables.types[var_id]
            if self._is_metric_variable(var_id):
               # assert self._is_cost_variable(var_name) 
                assert var_type == "I"    
            elif var_type == "R":
                var_mapping[var_id] = len(relevant_variable_names)
                relevant_variable_names.append(var_name)
                relevant_axiom_layers.append(var_axiom_layer)
                relevant_types.append(var_type)

        return (
            SASNumericVariables(
                relevant_variable_names,
                relevant_axiom_layers,
                relevant_types,
            ),
            var_mapping,
        )

    def get_relevant_init(self, sas_var_mapping, numeric_var_mapping):
        num_relevant_sas_vars = len(sas_var_mapping)
        assert(sorted(sas_var_mapping.values()) == list(range(num_relevant_sas_vars))), "SAS variable mapping is not dense"
        sas_var_mapping_inv = {new_id: old_id for old_id, new_id in sas_var_mapping.items()}
        sas_init = [
            self.sas_task.init.values[sas_var_mapping_inv[new_id]]
            for new_id in range(num_relevant_sas_vars)
        ]

        num_relevant_numeric_vars = len(numeric_var_mapping)
        assert(sorted(numeric_var_mapping.values()) == list(range(num_relevant_numeric_vars))), "Numeric variable mapping is not dense"
        numeric_var_mapping_inv = {new_id: old_id for old_id, new_id in numeric_var_mapping.items()}
        numeric_init = [
            self.sas_task.init.num_values[numeric_var_mapping_inv[new_id]]
            for new_id in range(num_relevant_numeric_vars)
        ]
        return SASInit(sas_init, numeric_init)

    def get_relevant_goal(self, sas_var_mapping, numeric_var_mapping):
        sas_goal = []
        numeric_goals = []
        goal_facts = self._unpack_goal_axioms()

        for fact in goal_facts:
            self._append_goal_fact(
                fact,
                sas_goal,
                numeric_goals,
                sas_var_mapping,
                numeric_var_mapping,
            )
        return sorted(set(sas_goal)), sorted(set(numeric_goals))

    def _append_operator_condition(
        self,
        fact: PropositionalAxiomSemanticsExtractor.Fact,
        sas_conditions: dict[int, int],
        numeric_preconditions: list[LinearCondition],
    ):
        for expanded_fact in self._expand_propositional_fact(fact):
            linear_condition = self._atom_to_linear_condition(expanded_fact)
            if linear_condition is not None:
                numeric_preconditions.append(
                    rename_numeric_condition(linear_condition, self.numeric_variable_mapping)
                )
                continue

            var_id, value = expanded_fact
            if var_id not in self.sas_variable_mapping:
                raise ValueError("Operator condition fact %s refers to SAS variable %s, which is not a retained original variable and was not resolved as a comparison or propositional-derived variable." % (expanded_fact, var_id))

            mapped_var = self.sas_variable_mapping[var_id]
            previous_value = sas_conditions.get(mapped_var)
            if previous_value is not None and previous_value != value:
                raise ValueError("Contradictory operator condition for variable %s" % mapped_var)
            sas_conditions[mapped_var] = value

    def _convert_operator(self, op: SASOperator):
        # 1. Collect all preconditions and expand them into sas conditions or numeric conditions.
        sas_conditions: dict[int, int] = {}
        numeric_preconditions: list[LinearCondition] = []
        for fact in op.prevail:
            self._append_operator_condition(
                fact,
                sas_conditions,
                numeric_preconditions,
            )
        prevail_condition_vars = set(sas_conditions) # vars mentioned in prevail conditions
        for var, pre, _post, _cond in op.pre_post: 
            if pre != -1: # If pre == -1, then there is no precondition
                self._append_operator_condition(
                    (var, pre),
                    sas_conditions,
                    numeric_preconditions,
                )

        # 2. Classify sas conditions into prevail or prepost
    
        # 2.1 Prepost conditions
        pre_post = [] # prepost conditions containing original SAS variables
        changed_vars = set() # Variables changed by prepost conditions
        for var, pre, post, cond in op.pre_post:
            if var not in self.sas_variable_mapping:
                raise ValueError("Prepost conditions on derived variables are not supported. Var: %s  Pre: %s  Post: %s" % (var, pre, post))
            assert not cond

            mapped_var = self.sas_variable_mapping[var]
            changed_vars.add(mapped_var)

            mapped_pre = sas_conditions.get(mapped_var, -1)
            if pre != -1 and mapped_pre != pre:
                raise ValueError(
                    "Inconsistent precondition for variable %s in operator %s: "
                    "pre_post requires %s, collected conditions require %s"
                    % (mapped_var, op.name, pre, mapped_pre)
                )
            pre_post.append((mapped_var, mapped_pre, post, []))


        # 2.2 Prevail conditions
        overlapping_vars = sorted(changed_vars & prevail_condition_vars) # Variables that should not be changed according to the prevail conditons, but that are changed by a prepost condition.
        if overlapping_vars:
            raise ValueError(
                "Operator %s has prevail conditions on changed variables %s"
                % (op.name, overlapping_vars)
            )
        prevail = sorted(
            (var, value)
            for var, value in sas_conditions.items()
            if var not in changed_vars # add all facts in sas_conditions that are not related to prepost conditions. 
        )


        # 3. Collect numeric effects
        numeric_effects = []
        for effect in op.assign_effects:
            old_var_id, ass_op, ass_var, cond = effect
            assert not cond
            
            # It can be the case that old_var_id represents an instrumentation variable. We deal with operator costs separately using _get_operator_cost
            if old_var_id not in self.numeric_variable_mapping:
                if self._is_metric_variable(old_var_id):
                    continue
                raise ValueError(
                    "Unsupported numeric effect on non-retained variable %s in operator %s"
                    % (old_var_id, op.name)
                )
            
            # We don't support a RHS containg an instrumentation variable (this probably never happens anyway)
            if self.sas_task.numeric_variables.types[ass_var] == "I":
                raise ValueError(
                    "Unsupported instrumentation variable %s on RHS of numeric effect in operator %s"
                    % (ass_var, op.name)
                )
            
            new_var_id = self.numeric_variable_mapping[old_var_id]
            
            linear_expression = self.semantics.numeric_semantics[ass_var]
            converted_linear_expression = rename_numeric_expression(linear_expression, self.numeric_variable_mapping)
            if ass_op == "=":
                effect_expression = converted_linear_expression
            elif ass_op == "+":
                effect_expression = LinearExpression({new_var_id: 1}, 0) + converted_linear_expression
            elif ass_op == "-":
                effect_expression = LinearExpression({new_var_id: 1}, 0) - converted_linear_expression
            else:
                assert False

            numeric_effects.append((new_var_id, effect_expression))

        return NumericOperator(
            op.name,
            prevail,
            pre_post,
            numeric_preconditions,
            numeric_effects,
            self._get_operator_cost(op)
        )

    def _get_operators(self):
        return [self._convert_operator(op) for op in self.sas_task.operators]

    def output(self, stream):
        sas_var_count = self.sas_variables.num()
        numeric_var_count = self.numeric_variables.num()

        print("begin_version", file=stream)
        print(4, file=stream)
        print("end_version", file=stream)
        print("begin_metric", file=stream)
        print(1, file=stream)
        print("end_metric", file=stream)

        print(sas_var_count, file=stream)
        for var, (rang, axiom_layer, values) in enumerate(zip(
            self.sas_variables.ranges,
            self.sas_variables.axiom_layers,
            self.sas_variables.value_names,
        )):
            print("begin_variable", file=stream)
            print("var%d" % var, file=stream)
            print(axiom_layer, file=stream)
            print(rang, file=stream)
            for value in values:
                print(value, file=stream)
            print("end_variable", file=stream)

        print(numeric_var_count, file=stream)
        for index, nvar_obj in enumerate(self.numeric_variables.variable_names):
            print("begin_numeric_variable", file=stream)
            print(nvar_obj.symbol, file=stream)
            print(self.numeric_variables.axiom_layers[index], file=stream)
            print("end_numeric_variable", file=stream)

        print(0, file=stream)

        print("begin_state", file=stream)
        for val in self.init.values:
            print(val, file=stream)
        print("end_state", file=stream)
        print("begin_numeric_state", file=stream)
        for val in self.init.num_values:
            print(val, file=stream)
        print("end_numeric_state", file=stream)

        goal_pairs = list(self.sas_goal_pairs)
        numeric_goals = list(self.numeric_goal_conditions)

        print("begin_goal", file=stream)
        print(len(goal_pairs), file=stream)
        for var, val in goal_pairs:
            print(var, val, file=stream)
        print("end_goal", file=stream)
        print("begin_numeric_goal", file=stream)
        print(len(numeric_goals), file=stream)
        for cond in numeric_goals:
            print(str(cond), file=stream)
        print("end_numeric_goal", file=stream)

        print(len(self.operators), file=stream)
        for op in self.operators:
            print("begin_operator", file=stream)
            print(op.name[1:-1], file=stream)
            print(len(op.prevail), file=stream)
            for var, val in op.prevail:
                print(var, val, file=stream)
            print(len(op.pre_post), file=stream)
            for var, pre, post, cond in op.pre_post:
                print(len(cond), end=" ", file=stream)
                for cvar, cval in cond:
                    print(cvar, cval, end=" ", file=stream)
                print(var, pre, post, file=stream)
            print(len(op.numeric_preconditions), file=stream)
            for cond in op.numeric_preconditions:
                print(str(cond), file=stream)
            print(len(op.numeric_effects), file=stream)
            for var, rhs in op.numeric_effects:
                print(f"{var} := {rhs}", file=stream)
            print(op.cost, file=stream)
            print("end_operator", file=stream)

        print(0, file=stream)
