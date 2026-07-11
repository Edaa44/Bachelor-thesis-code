from numeric_ir.linear_expr import LinearCondition, LinearExpression
from sas_tasks import SASTask

class PropositionalAxiomSemanticsExtractor:
    Fact = tuple[int, int]
    Conjunction = tuple[Fact, ...]

    def __init__(self, sas_task: SASTask) -> None:
        self.sas_task: SASTask = sas_task
        self.propositional_axioms_by_effect: dict[
            PropositionalAxiomSemanticsExtractor.Fact,
            list[list[PropositionalAxiomSemanticsExtractor.Fact]],
        ] = {}
        for pax in self.sas_task.axioms:
            self.propositional_axioms_by_effect.setdefault(pax.effect, []).append(pax.condition)
        self.propositional_semantic: dict[
            PropositionalAxiomSemanticsExtractor.Fact,
            PropositionalAxiomSemanticsExtractor.Conjunction,
        ] = self._get_propositional_derived_semantics()

    def _resolve_propositional_fact_semantic(self, fact: Fact, cache: dict[Fact, Conjunction], visiting: set[Fact],
    ) -> Conjunction:
        if fact in cache:
            return cache[fact]

        matching_axioms = self.propositional_axioms_by_effect.get(fact, [])
        if not matching_axioms:
            return (fact,)
        if len(matching_axioms) > 1:
            raise ValueError(
                "Unsupported disjunctive propositional axiom for fact %s" % (fact,)
            )
        if fact in visiting:
            raise ValueError(
                "Cyclic dependency detected while resolving propositional axiom for fact %s"
                % (fact,)
            )

        visiting.add(fact)
        resolved_condition: list[PropositionalAxiomSemanticsExtractor.Fact] = []
        for condition_fact in matching_axioms[0]:
            resolved_condition.extend(
                self._resolve_propositional_fact_semantic(
                    condition_fact,
                    cache,
                    visiting,
                )
            )
        visiting.remove(fact)

        by_variable: dict[int, int] = {}
        for var, value in resolved_condition:
            previous_value = by_variable.get(var)
            if previous_value is not None and previous_value != value:
                raise ValueError(
                    "Contradictory propositional axiom expansion for fact %s: "
                    "variable %s has values %s and %s"
                    % (fact, var, previous_value, value)
                )
            by_variable[var] = value

        resolved_condition = tuple(sorted(by_variable.items()))
        cache[fact] = resolved_condition
        return resolved_condition

    def _get_propositional_derived_semantics(self) -> dict[Fact, Conjunction]:
        semantics: dict[
            PropositionalAxiomSemanticsExtractor.Fact,
            PropositionalAxiomSemanticsExtractor.Conjunction,
        ] = {}
        for fact in self.propositional_axioms_by_effect:
            semantics[fact] = self._resolve_propositional_fact_semantic(fact, semantics, set())
        return semantics
    

class NumericAxiomSemanticsExtractor:
    """Resolve semantics for derived numeric and comparison variables."""

    def __init__(self, sas_task: SASTask):
        self.sas_task: SASTask = sas_task
        self.numeric_axioms_by_effect = {}
        for nax in self.sas_task.numeric_axioms:
            self.numeric_axioms_by_effect.setdefault(nax.effect, []).append(nax)
        self.comp_axioms_by_effect = {}
        for cax in self.sas_task.comp_axioms:
            self.comp_axioms_by_effect.setdefault(cax.effect, []).append(cax)
        self.numeric_semantics = self._get_numeric_derived_semantics()  # C numeric variables representing constants, D derived numeric variables representing expressions
        self.compare_semantics = self._get_compare_semantics()          # propositional variables representing conditions


    def _get_constant_value(self, nvar_id) -> int:
        numeric_var = self.sas_task.numeric_variables.variable_names[nvar_id]
        assert(numeric_var.ntype == "C")

        # Constants may be encoded symbolically (e.g. expressions over min/max).
        # The reliable source is the initialized numeric value in the SAS state.
        if nvar_id < len(self.sas_task.init.num_values):
            const = float(self.sas_task.init.num_values[nvar_id])
            #if not const.is_integer():
            #    raise ValueError(f"Constant value for variable {nvar_id} is not an integer: {const}")
            #return int(const)
            return const

        raise ValueError(
            f"Cannot extract constant value for numeric variable '{numeric_var.name}' with symbol '{numeric_var.symbol}'. "
            "This variable is declared as a constant but does not have an initial value."
        )

    def _resolve_numeric_variable_semantic(self, nvar_id, cache, visiting) -> LinearExpression:
        if nvar_id in cache:
            return cache[nvar_id]
        if nvar_id in visiting:
            raise ValueError(
                f"Cyclic dependency detected while resolving semantics for numeric variable {nvar_id}. "
                f"This indicates a cycle in the numeric axioms, which is not supported."
            )

        nvar_type = self.sas_task.numeric_variables.types[nvar_id]
        if nvar_type == "R":
            cache[nvar_id] = LinearExpression({nvar_id: 1}, 0)
            return cache[nvar_id]
        if nvar_type == "C":
            value = self._get_constant_value(nvar_id)
            cache[nvar_id] = LinearExpression({}, value)
            return cache[nvar_id]
        if nvar_type == "I":
            assert False, f"Internal numeric variable {nvar_id} should not occur in expressions."
        assert(nvar_type == "D")

        numeric_axioms = self.numeric_axioms_by_effect.get(nvar_id, [])
        assert(len(numeric_axioms) == 1)
        nax = numeric_axioms[0]
        assert(len(nax.parts) == 2)
        lhs_var_id = nax.parts[0]
        rhs_var_id = nax.parts[1]
        assert(nax.op in {"+", "-", "*"})

        visiting.add(nvar_id)
        lhs = self._resolve_numeric_variable_semantic(lhs_var_id, cache, visiting)
        rhs = self._resolve_numeric_variable_semantic(rhs_var_id, cache, visiting)
        visiting.remove(nvar_id)

        if nax.op == "+":
            cache[nvar_id] = lhs + rhs
        elif nax.op == "-":
            cache[nvar_id] = lhs - rhs
        elif nax.op == "*":
            if not rhs.coefficients:
                cache[nvar_id] = lhs * rhs.constant
            elif not lhs.coefficients:
                cache[nvar_id] = rhs * lhs.constant
            else:
                raise ValueError("Multiplication between variables is currently not supported: %s", (nax.op))
        else:
            raise ValueError("Unknown operation in numeric axiom. Affected variable: %s  Operation: %", (nax.effect. nax.op))
        return cache[nvar_id]

    def _get_numeric_derived_semantics(self) -> dict[int, LinearExpression]:
        semantics = {}
        for var_id, var_type in enumerate(self.sas_task.numeric_variables.types):
            if var_type != "I":
                self._resolve_numeric_variable_semantic(var_id, semantics, set())
        return semantics

    def _get_compare_semantics(self) -> dict[int, LinearCondition]:
        compare_var_semantics = {}
        for cax in self.sas_task.comp_axioms:
            assert(cax.comp in {"<", ">", "<=", ">=", "=", "!="})
            assert(len(cax.parts) == 2)
            lhs_var_id = cax.parts[0]
            rhs_var_id = cax.parts[1]
            assert(lhs_var_id in self.numeric_semantics)
            assert(rhs_var_id in self.numeric_semantics)
            lhs = self.numeric_semantics[lhs_var_id]
            rhs = self.numeric_semantics[rhs_var_id]
            comp = cax.comp
            if comp == "=":
                comp = "==" 
            compare_var_semantics[cax.effect] = LinearCondition(lhs, comp, rhs)

        return compare_var_semantics
