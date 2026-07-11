class LinearExpression:
    def __init__(self, coefficients, constant):
        self.coefficients = {var: coeff for var, coeff in coefficients.items() if coeff != 0}
        self.constant = constant

    def __str__(self):
        terms = []
        for var, coeff in self.coefficients.items():
            if coeff > 0:
                terms.append(f"+ {coeff}*{var}")
            elif coeff < 0:
                terms.append(f"- {-coeff}*{var}")
        if self.constant > 0:
            terms.append(f" + {self.constant}")
        elif self.constant < 0:
            terms.append(f" - {-self.constant}")
        if not terms:
            return "0"
        return " + ".join(terms)
    
    def __add__(self, other):
        new_coeffs = dict(self.coefficients)
        for var, coeff in other.coefficients.items():
            new_coeffs[var] = new_coeffs.get(var, 0) + coeff
        new_const = self.constant + other.constant
        return LinearExpression(new_coeffs, new_const)
    
    def __sub__(self, other):
        new_coeffs = dict(self.coefficients)
        for var, coeff in other.coefficients.items():
            new_coeffs[var] = new_coeffs.get(var, 0) - coeff
        new_const = self.constant - other.constant
        return LinearExpression(new_coeffs, new_const)
    
    def __mul__(self, scalar):
        new_coeffs = {var: coeff * scalar for var, coeff in self.coefficients.items()}
        new_const = self.constant * scalar
        return LinearExpression(new_coeffs, new_const)

    def __rmul__(self, scalar):
        return self.__mul__(scalar)

    def __neg__(self):
        return self.__mul__(-1)

    def __eq__(self, other):
        return self.coefficients == other.coefficients and self.constant == other.constant

    def __hash__(self):
        return hash((frozenset(self.coefficients.items()), self.constant))

class LinearCondition:
    def __init__(self, left_expr, comp, right_expr=None):
        # Avoid using a mutable default value; create the zero expression on demand.
        if right_expr is None:
            right_expr = LinearExpression({}, 0)
        # Normalize, so that the right expression is always zero.
        self.expr = left_expr - right_expr
        self.comp = comp
        assert self.comp in {"<=", "<", ">=", ">", "==", "!="}, "Unsupported comparison operator '%s'." % comp

    def negate(self):
        if self.comp == "<=":
            return LinearCondition(self.expr, ">")
        elif self.comp == "<":
            return LinearCondition(self.expr, ">=")
        elif self.comp == ">=":
            return LinearCondition(self.expr, "<")
        elif self.comp == ">":
            return LinearCondition(self.expr, "<=")
        elif self.comp == "==":
            return LinearCondition(self.expr, "!=")
        elif self.comp == "!=":
            return LinearCondition(self.expr, "==")
        else:
            raise ValueError("Unsupported comparison operator '%s'." % self.comp)

    def __str__(self):
        return f"{self.expr} {self.comp} 0"
    
    def __eq__(self, other):
        return isinstance(other, LinearCondition) and self.comp == other.comp and self.expr == other.expr

    def __hash__(self):
        return hash((self.expr, self.comp))

    def __lt__(self, other):
        # Provide a deterministic ordering for sorting; use string form.
        return str(self) < str(other)