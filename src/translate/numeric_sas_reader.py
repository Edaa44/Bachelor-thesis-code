from dataclasses import dataclass
from typing import Dict, List, Tuple



@dataclass
class LinearExpr:
    coeffs: Dict[int, float]   # numeric var index -> coefficient
    const: float

    def evaluate(self, nu: List[float]) -> float:
        return sum(k * nu[i] for i, k in self.coeffs.items()) + self.const


def parse_linear_expr(tokens: List[str], pos: int) -> Tuple[LinearExpr, int]:
    #this is for parsing the precondition and effect expressions in the numeric SAS format. 
    # takes a list of tokens and a starting position, and returns a LinearExpr object and the new position after parsing.
    """Parses '+ 1*0 +  - 50.0' style terms until a comparator or end."""
    coeffs, const = {}, 0.0
    sign = 1.0
    while pos < len(tokens):
        tok = tokens[pos]
        if tok == '+':
            sign = 1.0; pos += 1
        elif tok == '-':
            sign = -1.0; pos += 1
        elif tok in ('>=', '<=', '=='):  #if token is a comparator, we mostly compare to zero, so end. 
            break
        elif '*' in tok:
            coeff_str, var_str = tok.split('*')
            v = int(var_str)
            coeffs[v] = coeffs.get(v, 0.0) + sign * float(coeff_str)
            sign = 1.0; pos += 1
        else:
            const += sign * float(tok)
            sign = 1.0; pos += 1
    return LinearExpr(coeffs, const), pos

#this is a class that reads a numeric SAS file and parses it into a dictionary representation 
# of the task. It handles variables, goals, operators, and other components of the SAS format.
# made to make the format to translate same to the theory part in my thesis.

class NumericSASReader:
    def __init__(self, lines: List[str]):
        self.lines = [l.rstrip('\n') for l in lines]
        self.pos = 0

    def _next(self) -> str: #return the next line and advance the position
        line = self.lines[self.pos].strip()
        self.pos += 1
        return line

    def _expect(self, tag: str):
        line = self._next()
        assert line == tag, f"expected {tag!r}, got {line!r} at line {self.pos}"

    def _read_block(self, begin_tag, end_tag) -> List[str]:
        self._expect(begin_tag)
        content = []
        while self.lines[self.pos].strip() != end_tag:
            content.append(self._next())
        self._expect(end_tag)
        return content

    def parse(self) -> dict:
        self._read_block("begin_version", "end_version")
        metric_lines = self._read_block("begin_metric", "end_metric")
        metric = bool(int(metric_lines[0]))

        n_prop = int(self._next())
        prop_vars = [] #we take the variables and store them in a list of dictionaries, each containing the name, layer, and values of the variable
        for _ in range(n_prop):
            b = self._read_block("begin_variable", "end_variable")
            name, layer, rang = b[0], int(b[1]), int(b[2])
            values = b[3:3 + rang]
            prop_vars.append({"name": name, "layer": layer, "values": values})

        n_num = int(self._next())
        num_vars = [] #same for numeric
        for _ in range(n_num):
            b = self._read_block("begin_numeric_variable", "end_numeric_variable")
            num_vars.append({"name": b[0], "layer": int(b[1]), "bounds": None})

        n_mutex = int(self._next())
        for _ in range(n_mutex): 
            self._read_block("begin_mutex_group", "end_mutex_group")

        prop_init = [int(x) for x in self._read_block("begin_state", "end_state")] #ex: [0,1,0,1]
        num_init = [float(x) for x in self._read_block("begin_numeric_state", "end_numeric_state")] #ex:[20.0]

        goal_block = self._read_block("begin_goal", "end_goal")
        n_goal = int(goal_block[0])
        prop_goal = []   
        for line in goal_block[1:1 + n_goal]: #ex: [(3, 0)], var3 (museum-visited) = value 0 (true)
            var, val = line.split()
            prop_goal.append((int(var), int(val)))

        ng_block = self._read_block("begin_numeric_goal", "end_numeric_goal")
        n_ng = int(ng_block[0])
        num_goal = []
        for line in ng_block[1:1 + n_ng]:
            tokens = line.split()
            expr, pos = parse_linear_expr(tokens, 0)
            op = tokens[pos]
            num_goal.append((expr, op))

        n_ops = int(self._next())
        operators = []
        #each dictionary for pre_p pre_n, eff_p, eff_n
        for _ in range(n_ops):
            self._expect("begin_operator")
            name = self._next()
            n_prevail = int(self._next())
            prevail = []
            for _ in range(n_prevail):
                var, val = self._next().split()
                prevail.append((int(var), int(val)))

            n_pre_post = int(self._next())
            pre_post = []
            for _ in range(n_pre_post):
                parts = self._next().split()
                cond_count = int(parts[0])
                idx = 1
                cond = []
                for _ in range(cond_count):
                    cond.append((int(parts[idx]), int(parts[idx + 1])))
                    idx += 2
                var, pre, post = int(parts[idx]), int(parts[idx + 1]), int(parts[idx + 2])
                pre_post.append((var, pre, post, cond))

            n_num_pre = int(self._next())
            num_pre = []
            for _ in range(n_num_pre):
                tokens = self._next().split()
                expr, pos = parse_linear_expr(tokens, 0)
                op = tokens[pos]
                num_pre.append((expr, op))

            n_num_eff = int(self._next())
            num_eff = []
            for _ in range(n_num_eff):
                tokens = self._next().split()
                target_var = int(tokens[0])
                assert tokens[1] == ':=', tokens
                expr, _ = parse_linear_expr(tokens, 2)
                num_eff.append((target_var, expr))

            cost = int(self._next())
            self._expect("end_operator")
            operators.append({
                "name": name, "prevail": prevail, "pre_post": pre_post,
                "num_pre": num_pre, "num_eff": num_eff, "cost": cost,
            })

        n_axioms = int(self._next())
        # no axiom parsing yet — none in this example

        return {
            "metric": metric, "prop_vars": prop_vars, "num_vars": num_vars,
            "prop_init": prop_init, "num_init": num_init,
            "prop_goal": prop_goal, "num_goal": num_goal,
            "operators": operators, "n_axioms": n_axioms,
        }


def parse_numeric_sas(path: str) -> dict:
    with open(path) as f:
        lines = f.readlines()
    return NumericSASReader(lines).parse()


if __name__ == "__main__":
    import sys, pprint
    result = parse_numeric_sas(sys.argv[1])
    pprint.pprint(result)
