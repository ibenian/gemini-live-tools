"""
math_eval.py — Safe math expression evaluator with optional NumPy linalg support.

Evaluates arithmetic and math-function expressions from untrusted input.
Uses AST whitelisting: only numeric literals, arithmetic operators, and an
explicit set of math/linalg functions are permitted. No builtins, no
attribute access, no imports, no comprehensions — nothing else.

Scalar usage:
    result, error = safe_eval_math("sqrt(3**2 + 4**2)")
    # result = 5.0

    result, error = safe_eval_math("ax*bx + ay*by", {"ax": 1, "ay": 2, "bx": 3, "by": 4})
    # result = 11.0

Vector/matrix usage (requires numpy):
    result, error = safe_eval_math("norm(a)", {"a": [3, 4]})
    # result = 5.0

    result, error = safe_eval_math("A @ b", {"A": [[1,2],[3,4]], "b": [1,1]})
    # result = [3.0, 7.0]

Self-documenting:
    result, error = safe_eval_math("help()")          # list all functions
    result, error = safe_eval_math("help('eig')")     # docs for eig

Security — all blocked:
    safe_eval_math("__import__('os')")    # Unknown function: '__import__'
    safe_eval_math("[x for x in []]")    # Disallowed: ListComp
"""

import ast
import math

# ---------------------------------------------------------------------------
# Resource limits — prevent DoS via unbounded computation
# ---------------------------------------------------------------------------

# Max length of the expression string (characters).
_MAX_EXPR_LEN = 500

# Max integer result bit-length for the ** operator.
# 65 536 bits ≈ 19 700 decimal digits — far larger than any legitimate math
# result, yet small enough to prevent memory exhaustion.
_MAX_RESULT_BITS = 65_536

# Max argument to factorial().
# factorial(20 000) completes in under a second and produces ~77 000 digits.
_MAX_FACTORIAL_ARG = 20_000

# Max repetition multiplier for list/string * int.
_MAX_SEQ_REPEAT = 10_000

# Max number of sweep points in eval_math_sweep.
_MAX_SWEEP_STEPS = 100_000

# ---------------------------------------------------------------------------
# NumPy — optional, enables linalg functions
# ---------------------------------------------------------------------------

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False

# ---------------------------------------------------------------------------
# Per-function documentation
# Each entry: 'name': 'signature — description. Returns: type. Example: ...'
# ---------------------------------------------------------------------------

MATH_DOCS = {
    # Constants
    'pi':  'pi — π ≈ 3.14159',
    'e':   'e — Euler\'s number ≈ 2.71828',
    'tau': 'tau — τ = 2π ≈ 6.28318',
    'inf': 'inf — floating-point infinity',

    # Scalar
    'abs':       'abs(x) — absolute value. Example: abs(-3) = 3',
    'round':     'round(x, n) — round to n decimal places. Example: round(1.567, 2) = 1.57',
    'floor':     'floor(x) — largest integer ≤ x. Example: floor(2.9) = 2',
    'ceil':      'ceil(x) — smallest integer ≥ x. Example: ceil(2.1) = 3',
    'min':       'min(a, b, ...) — minimum value',
    'max':       'max(a, b, ...) — maximum value',
    'sum':       'sum(iterable) — sum of elements',
    'range':     'range(stop) / range(start, stop[, step]) — bounded integer range for simple list comprehensions.',
    'pow':       'pow(x, y) — x raised to y',
    'factorial': f'factorial(n) — n! (max n={_MAX_FACTORIAL_ARG}). Example: factorial(5) = 120',
    'gcd':       'gcd(a, b) — greatest common divisor. Example: gcd(12, 8) = 4',

    # Roots / exponentials
    'sqrt':  'sqrt(x) — square root. Example: sqrt(9) = 3.0',
    'cbrt':  'cbrt(x) — cube root. Example: cbrt(27) = 3.0',
    'exp':   'exp(x) — e^x. Example: exp(1) = 2.71828',
    'log':   'log(x) or log(x, base) — natural log or log base b. Example: log(e) = 1.0',
    'log2':  'log2(x) — log base 2. Example: log2(8) = 3.0',
    'log10': 'log10(x) — log base 10. Example: log10(1000) = 3.0',

    # Trigonometry
    'sin':     'sin(x) — sine of x (radians)',
    'cos':     'cos(x) — cosine of x (radians)',
    'tan':     'tan(x) — tangent of x (radians)',
    'asin':    'asin(x) — arcsine, returns radians in [-π/2, π/2]',
    'acos':    'acos(x) — arccosine, returns radians in [0, π]',
    'atan':    'atan(x) — arctangent, returns radians in (-π/2, π/2)',
    'atan2':   'atan2(y, x) — angle of vector (x,y) from +x axis, in radians. Example: degrees(atan2(1,1)) = 45',
    'sinh':    'sinh(x) — hyperbolic sine',
    'cosh':    'cosh(x) — hyperbolic cosine',
    'tanh':    'tanh(x) — hyperbolic tangent',
    'hypot':   'hypot(a, b, ...) — Euclidean distance. Example: hypot(3, 4) = 5.0',
    'degrees': 'degrees(x) — convert radians to degrees. Example: degrees(pi) = 180.0',
    'radians': 'radians(x) — convert degrees to radians. Example: radians(180) = π',

    # Vector construction
    'vec':   'vec([x,y,z]) — create a numpy array (vector) from a list literal inside an expression. Example: norm(vec([3,4,0]))',
    'array': 'array([...]) — alias for vec()',
    'zeros': 'zeros(n) or zeros((m,n)) — zero vector or matrix. Returns: ndarray',
    'ones':  'ones(n) or ones((m,n)) — ones vector or matrix. Returns: ndarray',
    'eye':   'eye(n) — n×n identity matrix. Returns: ndarray. Example: eye(3)',

    # Vector operations
    'dot':       'dot(a, b) → scalar — dot product. Example: dot([1,2,3],[4,5,6]) = 32',
    'cross':     'cross(a, b) → vector — cross product (3D). Example: cross([1,0,0],[0,1,0]) = [0,0,1]',
    'outer':     'outer(a, b) → matrix — outer product. Returns m×n matrix.',
    'matmul':    'matmul(A, B) → matrix — matrix multiply. Same as A @ B.',
    'norm':      'norm(v) → scalar — Euclidean magnitude. Example: norm([3,4]) = 5.0',
    'normalize': 'normalize(v) → vector — unit vector in direction of v. Example: normalize([3,4]) = [0.6, 0.8]',
    'angle':     'angle(a, b) → scalar — angle between vectors in degrees. Example: angle([1,0],[0,1]) = 90.0',
    'proj':      'proj(a, b) → vector — projection of a onto b. Returns vector component of a along b.',

    # Matrix operations
    'transpose': 'transpose(A) → matrix — matrix transpose.',
    'trace':     'trace(A) → scalar — sum of diagonal elements.',
    'det':       'det(A) → scalar — determinant. Example: det([[1,2],[3,4]]) = -2.0',
    'inv':       'inv(A) → matrix — matrix inverse. A must be square and non-singular.',
    'rank':      'rank(A) → int — matrix rank.',
    'reshape':   'reshape(a, shape) — reshape array. Example: reshape([1,2,3,4], (2,2))',
    'flatten':   'flatten(a) → 1D array — flatten to 1D. Handles nested/ragged lists of vectors by concatenating flattened parts.',
    'concat_rows': 'concat_rows(a, b, ...) → matrix — row-wise concatenate 2D arrays (same column count). Useful for joining point clouds with different row counts.',

    # Solvers / decompositions
    'solve': (
        'solve(A, b) → vector — solve linear system Ax = b. '
        'Returns: x (solution vector). Example: solve([[2,1],[1,3]], [5,10]) → [1.0, 3.0]'
    ),
    'eig': (
        'eig(A) → (eigenvalues, eigenvectors) — eigendecomposition. '
        'Returns: tuple [eigenvalues_array, eigenvectors_matrix] where each column is an eigenvector. '
        'Example: eig([[2,1],[1,2]]) → [[1.0, 3.0], [[0.707,-0.707],[0.707,0.707]]]'
    ),
    'svd': (
        'svd(A) → (U, S, Vt) — singular value decomposition. '
        'Returns: tuple [U_matrix, singular_values, Vt_matrix]. A = U @ diag(S) @ Vt.'
    ),
    'qr': (
        'qr(A) → (Q, R) — QR decomposition. '
        'Returns: tuple [Q_orthogonal_matrix, R_upper_triangular_matrix].'
    ),
}

# ---------------------------------------------------------------------------
# Safe wrappers — enforce resource limits at call time
# ---------------------------------------------------------------------------

def _safe_factorial(n):
    """Bounded factorial. Raises ValueError when n > _MAX_FACTORIAL_ARG."""
    if isinstance(n, float):
        if not n.is_integer():
            raise ValueError(f"factorial requires an integer argument, got {n!r}")
        n = int(n)
    if not isinstance(n, int):
        raise TypeError(f"factorial requires an integer, got {type(n).__name__}")
    if n < 0:
        raise ValueError("factorial is not defined for negative numbers")
    if n > _MAX_FACTORIAL_ARG:
        raise ValueError(
            f"factorial({n}) exceeds maximum allowed argument ({_MAX_FACTORIAL_ARG})"
        )
    return math.factorial(n)


def _safe_pow(base, exp):
    """Bounded exponentiation. Raises ValueError when the integer result would be too large."""
    if isinstance(base, int) and isinstance(exp, int) and exp > 0 and abs(base) > 1:
        try:
            estimated_bits = exp * math.log2(abs(base))
        except (ValueError, OverflowError):
            estimated_bits = float('inf')
        if estimated_bits >= _MAX_RESULT_BITS:
            raise ValueError(
                f"Result too large: {base}**{exp} would require ~{estimated_bits:.0f} bits "
                f"(max {_MAX_RESULT_BITS}). Use float arithmetic: float({base})**{exp}."
            )
    return base ** exp


def _safe_mul(a, b):
    """Multiplication with a sequence-repetition guard."""
    if isinstance(a, (str, bytes, list, tuple)) and isinstance(b, int) and b > _MAX_SEQ_REPEAT:
        raise ValueError(
            f"Sequence repetition too large: *{b} (max {_MAX_SEQ_REPEAT})"
        )
    if isinstance(b, (str, bytes, list, tuple)) and isinstance(a, int) and a > _MAX_SEQ_REPEAT:
        raise ValueError(
            f"Sequence repetition too large: *{a} (max {_MAX_SEQ_REPEAT})"
        )
    return a * b


# ---------------------------------------------------------------------------
# AST transformer — replace ** and * with safe wrappers before evaluation
# ---------------------------------------------------------------------------

class _SafeOpsTransformer(ast.NodeTransformer):
    """Replace x**y with _safe_pow(x, y) and x*y with _safe_mul(x, y)."""

    def visit_BinOp(self, node):
        self.generic_visit(node)  # recurse into children first
        if isinstance(node.op, ast.Pow):
            return ast.Call(
                func=ast.Name(id='_safe_pow', ctx=ast.Load()),
                args=[node.left, node.right],
                keywords=[],
            )
        if isinstance(node.op, ast.Mult):
            return ast.Call(
                func=ast.Name(id='_safe_mul', ctx=ast.Load()),
                args=[node.left, node.right],
                keywords=[],
            )
        return node


# ---------------------------------------------------------------------------
# help() — callable from within expressions
# ---------------------------------------------------------------------------

def _help(name=None):
    """Return documentation as a string. Called as help() or help('funcname')."""
    if name is None:
        # Grouped summary
        constants = sorted(k for k, v in MATH_NAMES.items() if isinstance(v, (int, float)))
        functions = sorted(k for k in MATH_NAMES if k not in constants and k != 'help')
        lines = [
            "=== math_eval available names ===",
            f"Constants: {', '.join(constants)}",
            f"Functions: {', '.join(functions)}",
            "",
            "Call help('name') for details on any function.",
            "Example expressions:",
            "  norm(a)                           → magnitude of vector a",
            "  dot(a, b)                         → dot product",
            "  angle(a, b)                       → angle in degrees",
            "  solve(A, b)                       → solution to Ax=b",
            "  eig(A)                            → eigenvalues and eigenvectors",
            "  degrees(atan2(ay, ax))            → angle of 2D vector",
            "  sqrt(ax**2 + ay**2 + az**2)       → 3D magnitude using slider vars",
        ]
        return '\n'.join(lines)

    name = str(name)
    if name in MATH_DOCS:
        return MATH_DOCS[name]
    if name in MATH_NAMES:
        return f"{name}: available (no detailed docs yet)"
    return f"Unknown: '{name}'. Call help() for full listing."

# ---------------------------------------------------------------------------
# Whitelisted scalar math names
# ---------------------------------------------------------------------------

MATH_NAMES = {
    # Constants
    'pi':  math.pi,
    'e':   math.e,
    'inf': math.inf,
    'tau': math.tau,
    # Basic
    'abs':       abs,
    'round':     round,
    'min':       min,
    'max':       max,
    'sum':       sum,
    'range':     None,  # set below to bounded helper
    'pow':       math.pow,
    # Rounding / integer
    'floor':     math.floor,
    'ceil':      math.ceil,
    'factorial': _safe_factorial,
    'gcd':       math.gcd,
    # Roots / exponentials
    'sqrt':  math.sqrt,
    'cbrt':  math.cbrt if hasattr(math, 'cbrt') else (lambda x: x ** (1 / 3)),
    'exp':   math.exp,
    'log':   math.log,
    'log2':  math.log2,
    'log10': math.log10,
    # Trigonometry
    'sin':     math.sin,
    'cos':     math.cos,
    'tan':     math.tan,
    'asin':    math.asin,
    'acos':    math.acos,
    'atan':    math.atan,
    'atan2':   math.atan2,
    'sinh':    math.sinh,
    'cosh':    math.cosh,
    'tanh':    math.tanh,
    'hypot':   math.hypot,
    'degrees': math.degrees,
    'radians': math.radians,
    # Self-documentation
    'help':    _help,
}


def _safe_range(*args):
    """Bounded range helper for math expressions/list comprehensions."""
    if len(args) not in (1, 2, 3):
        raise ValueError("range expects 1-3 integer arguments")
    try:
        ints = tuple(int(a) for a in args)
    except (TypeError, ValueError):
        raise ValueError("range arguments must be integers")
    r = range(*ints)
    # Keep evaluation bounded to avoid accidental huge outputs.
    if len(r) > 10000:
        raise ValueError("range too large (max 10000 items)")
    return r


MATH_NAMES['range'] = _safe_range

# ---------------------------------------------------------------------------
# Whitelisted linalg names (numpy-backed, only added when numpy is available)
# ---------------------------------------------------------------------------

if HAS_NUMPY:
    def _flatten_safe(a):
        """
        Flatten nested arrays/lists safely, including ragged list-of-arrays.
        Examples:
          flatten([[1,2],[3,4]]) -> [1,2,3,4]
          flatten([arr_64x3, arr_32x3]) -> 288-length vector
        """
        if isinstance(a, np.ndarray):
            return a.reshape(-1)
        if isinstance(a, (list, tuple)):
            pieces = [_flatten_safe(x) for x in a]
            pieces = [p for p in pieces if getattr(p, "size", 0) > 0]
            if not pieces:
                return np.array([], dtype=float)
            return np.concatenate(pieces)
        return np.asarray(a, dtype=float).reshape(-1)

    def _concat_rows(*arrays):
        """
        Row-wise concatenate arrays with matching column counts.
        1D inputs are treated as single-row matrices.
        """
        mats = []
        for a in arrays:
            arr = np.asarray(a, dtype=float)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            elif arr.ndim != 2:
                raise ValueError(f"concat_rows expects 1D/2D inputs, got {arr.ndim}D")
            mats.append(arr)
        if not mats:
            return np.empty((0, 0), dtype=float)
        cols = mats[0].shape[1]
        for m in mats[1:]:
            if m.shape[1] != cols:
                raise ValueError(
                    f"concat_rows column mismatch: expected {cols}, got {m.shape[1]}"
                )
        return np.vstack(mats)

    def _angle(a, b):
        a, b = np.asarray(a, float), np.asarray(b, float)
        cos = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))

    def _proj(a, b):
        b = np.asarray(b, float)
        return (np.dot(a, b) / np.dot(b, b)) * b

    LINALG_NAMES = {
        # Array construction
        'vec':       np.array,
        'array':     np.array,
        'zeros':     np.zeros,
        'ones':      np.ones,
        'eye':       np.eye,
        # Products
        'dot':       np.dot,
        'cross':     np.cross,
        'matmul':    np.matmul,
        'outer':     np.outer,
        # Norms / metrics
        'norm':      np.linalg.norm,
        'angle':     _angle,
        # Decompositions / solvers
        'inv':       np.linalg.inv,
        'det':       np.linalg.det,
        'solve':     np.linalg.solve,
        'eig':       np.linalg.eig,
        'svd':       np.linalg.svd,
        'qr':        np.linalg.qr,
        # Transformations
        'transpose': np.transpose,
        'reshape':   np.reshape,
        'flatten':   _flatten_safe,
        'concat_rows': _concat_rows,
        'normalize': lambda v: np.asarray(v, float) / np.linalg.norm(v),
        'proj':      _proj,
        # Reductions
        'trace':     np.trace,
        'rank':      np.linalg.matrix_rank,
    }
    MATH_NAMES.update(LINALG_NAMES)

# ---------------------------------------------------------------------------
# Whitelisted AST node types
# ---------------------------------------------------------------------------

_ALLOWED_NODES = tuple(filter(None, [
    ast.Expression,
    ast.ListComp, ast.comprehension,
    ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp,
    ast.Call,
    ast.Constant,
    getattr(ast, 'Num', None),    # removed in Python 3.12
    ast.Name,
    ast.List, ast.Tuple,
    ast.Subscript,                # a[0], a[1] — vector component access
    ast.Slice,                    # a[i:j[:k]] — bounded array/list slicing
    getattr(ast, 'ExtSlice', None),  # removed in newer Python, keep compat
    getattr(ast, 'Index', None),  # removed in Python 3.9 (wraps subscript index)
    # Operators
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.MatMult,                  # @ operator for matrix multiply
    ast.USub, ast.UAdd,
    # Comparisons / logic
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.And, ast.Or, ast.Not,
    ast.Load, ast.Store,
]))

# ---------------------------------------------------------------------------
# Result serialization — convert numpy types to plain Python for JSON
# ---------------------------------------------------------------------------

def _to_python(obj):
    if isinstance(obj, range):
        return list(obj)
    if HAS_NUMPY:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.complexfloating):
            return complex(obj)
    if isinstance(obj, (list, tuple)):
        return [_to_python(x) for x in obj]
    return obj

# ---------------------------------------------------------------------------
# Variable coercion — accept scalars, lists, and numpy arrays
# ---------------------------------------------------------------------------

def _coerce_var(k, v):
    """Return (coerced_value, error_string). Accepts int/float/list/ndarray."""
    if isinstance(v, bool):
        return int(v), None
    if isinstance(v, int):
        return int(v), None
    if isinstance(v, float):
        return float(v), None
    if isinstance(v, range):
        v = list(v)
    if isinstance(v, (list, tuple)):
        if not HAS_NUMPY:
            # Fallback mode without NumPy: keep native sequence support so
            # indexing/slicing/comprehensions still work.
            return list(v), None
        return np.array(v, dtype=float), None
    if HAS_NUMPY and isinstance(v, np.ndarray):
        return v.astype(float), None
    return None, f"Variable '{k}' has unsupported type {type(v).__name__}"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def safe_eval_math(expr: str, variables: dict | None = None):
    """
    Safely evaluate a math expression.

    Args:
        expr:      Expression string, e.g. "norm(a - b)" or "help('eig')".
        variables: Optional dict of name → value. Scalars (int/float) and
                   vectors/matrices (list or np.ndarray) are both accepted.

    Returns:
        (result, None)        on success; result is scalar, list, nested list, or string (for help)
        (None,  error_str)    on any error
    """
    # --- Guard: expression length (checked before parsing to prevent slow parse) ---
    if len(expr) > _MAX_EXPR_LEN:
        return None, (
            f"Expression too long ({len(expr)} chars; max {_MAX_EXPR_LEN})"
        )

    try:
        tree = ast.parse(expr.strip(), mode='eval')
    except SyntaxError as exc:
        return None, f"Syntax error: {exc}"

    all_names = set(MATH_NAMES) | set(variables or {})
    comp_locals = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ListComp):
            for gen in n.generators:
                if isinstance(gen.target, ast.Name):
                    comp_locals.add(gen.target.id)

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            return None, f"Disallowed operation: {type(node).__name__}"
        # Guard: reject oversized string literals (they cannot appear in the
        # transformed AST either, so this check stays on the original tree).
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if len(node.value) > 200:
                return None, (
                    f"String literal too long ({len(node.value)} chars; max 200)"
                )
        if isinstance(node, ast.ListComp):
            # Restrict list comprehensions to one simple generator with no filters.
            # Allowed iterables:
            #   1) range(...)
            #   2) an existing sequence variable (list/tuple/range/ndarray)
            # to support memory-backed workflows like: [i*10 for i in my_array]
            # while keeping evaluation tightly bounded.
            if len(node.generators) != 1:
                return None, "List comprehensions must use exactly one generator"
            gen = node.generators[0]
            if gen.is_async:
                return None, "Async comprehensions are not allowed"
            if gen.ifs:
                return None, "Comprehension filters are not allowed"
            if not isinstance(gen.target, ast.Name):
                return None, "Comprehension target must be a simple variable name"
            if (
                isinstance(gen.iter, ast.Call)
                and isinstance(gen.iter.func, ast.Name)
                and gen.iter.func.id == 'range'
            ):
                pass
            elif isinstance(gen.iter, ast.Name):
                if not variables or gen.iter.id not in variables:
                    return None, (
                        f"Comprehension iterable '{gen.iter.id}' must be an existing variable "
                        f"(or use range(...))"
                    )
                raw_iter = variables.get(gen.iter.id)
                seq_len = None
                if isinstance(raw_iter, range):
                    seq_len = len(raw_iter)
                elif isinstance(raw_iter, (list, tuple)):
                    seq_len = len(raw_iter)
                elif HAS_NUMPY and isinstance(raw_iter, np.ndarray):
                    if raw_iter.ndim == 0:
                        return None, (
                            f"Comprehension iterable '{gen.iter.id}' must be 1D/2D array-like, "
                            f"got scalar ndarray"
                        )
                    seq_len = raw_iter.shape[0]
                else:
                    return None, (
                        f"Comprehension iterable '{gen.iter.id}' has unsupported type "
                        f"{type(raw_iter).__name__}; use range(...) or an array/list variable"
                    )
                if seq_len is not None and seq_len > 10000:
                    return None, (
                        f"Comprehension iterable '{gen.iter.id}' too large "
                        f"(max 10000 items)"
                    )
            else:
                return None, (
                    "List comprehensions must iterate over range(...) or an existing "
                    "sequence variable"
                )
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                obj  = node.func.value.id if isinstance(node.func.value, ast.Name) else '?'
                # Give a targeted hint for JS-style Math.xxx calls
                if obj in ('Math', 'math', 'np', 'numpy', 'linalg'):
                    return None, (
                        f"Use Python syntax: '{attr}(...)' not '{obj}.{attr}(...)'. "
                        f"All functions are available as bare names (e.g. sin, cos, sqrt, norm)."
                    )
                return None, (
                    f"Attribute calls not allowed. Use bare function names: "
                    f"'sin(x)' not 'Math.sin(x)', 'sqrt(x)' not 'Math.sqrt(x)'."
                )
            elif not isinstance(node.func, ast.Name):
                return None, "Attribute calls not allowed — use bare function names like sin(x), sqrt(x)"
            if node.func.id not in all_names:
                return None, f"Unknown function: '{node.func.id}'"
        if isinstance(node, ast.Name):
            if node.id not in all_names and node.id not in comp_locals:
                return None, f"Unknown name: '{node.id}'"

    namespace = dict(MATH_NAMES)
    if variables:
        for k, v in variables.items():
            coerced, err = _coerce_var(k, v)
            if err:
                return None, err
            namespace[k] = coerced

    # Apply AST transformer: rewrite x**y → _safe_pow(x,y) and x*y → _safe_mul(x,y).
    # This happens AFTER whitelist validation so the injected Call nodes do not
    # need to appear in all_names. The private wrappers are added to the namespace
    # directly and are never callable by user expressions (they start with '_').
    tree = _SafeOpsTransformer().visit(tree)
    ast.fix_missing_locations(tree)
    namespace['_safe_pow'] = _safe_pow
    namespace['_safe_mul'] = _safe_mul

    try:
        result = eval(compile(tree, '<math>', 'eval'), {"__builtins__": {}}, namespace)
        return _to_python(result), None
    except ZeroDivisionError:
        return None, "Division by zero"
    except Exception as exc:
        msg = str(exc)
        # Helpful fallback: users often mean "join rows" when adding point arrays
        # with different row counts, e.g. (64,3) + (32,3).
        if HAS_NUMPY and "could not be broadcast together with shapes" in msg:
            try:
                body = tree.body
                if isinstance(body, ast.BinOp) and isinstance(body.op, ast.Add):
                    left = eval(compile(ast.Expression(body.left), '<math-left>', 'eval'), {"__builtins__": {}}, namespace)
                    right = eval(compile(ast.Expression(body.right), '<math-right>', 'eval'), {"__builtins__": {}}, namespace)
                    if (
                        isinstance(left, np.ndarray)
                        and isinstance(right, np.ndarray)
                        and left.ndim == 2
                        and right.ndim == 2
                        and left.shape[1] == right.shape[1]
                    ):
                        return _to_python(_concat_rows(left, right)), None
            except Exception:
                pass
            return None, msg + " Hint: for joining point arrays, use concat_rows(a, b) instead of a + b."
        return None, msg


def eval_math_sweep(expr: str, variables: dict | None = None, sweep: dict | None = None):
    """
    Evaluate a math expression at each point in a sweep of one variable.

    Args:
        expr:      Expression string, same syntax as safe_eval_math.
        variables: Base variable bindings (scalars/vectors/matrices). Evaluated once.
        sweep:     Dict with exactly one entry: {var_name: spec} where spec is either:
                     - a list of explicit sample values, e.g. [0, 0.5, 1.0, 1.5]
                     - a dict {"start": 0, "end": 6.28, "steps": 100} for a linspace

    Returns:
        (results, None)   on success; results is a list with one entry per sample point
        (None, error_str) on any error (including per-point errors)

    Example:
        eval_math_sweep(
            "[2*cos(t) - sin(t), 2*sin(t) + cos(t), 0]",
            sweep={"t": {"start": 0, "end": 6.28318, "steps": 64}}
        )
        # returns a list of 64 [x, y, z] lists tracing the rotated vector
    """
    if not sweep:
        return safe_eval_math(expr, variables)

    if len(sweep) != 1:
        return None, "sweep must contain exactly one variable"

    var_name, spec = next(iter(sweep.items()))

    def _coerce_point(x):
        # Preserve integers for index-friendly sweeps, keep non-integers as float.
        xf = float(x)
        if abs(xf - round(xf)) < 1e-12:
            return int(round(xf))
        return xf

    if isinstance(spec, list):
        if len(spec) > _MAX_SWEEP_STEPS:
            return None, (
                f"sweep values list too large: {len(spec)} points (max {_MAX_SWEEP_STEPS})"
            )
        points = [_coerce_point(x) for x in spec]
    elif isinstance(spec, dict):
        try:
            start = float(spec['start'])
            end   = float(spec['end'])
            steps = int(spec.get('steps', 100))
        except (KeyError, TypeError, ValueError) as exc:
            return None, f"sweep spec error: {exc} — expected {{start, end, steps}}"
        if steps < 2:
            return None, "sweep steps must be >= 2"
        if steps > _MAX_SWEEP_STEPS:
            return None, f"sweep steps too large: {steps} (max {_MAX_SWEEP_STEPS})"
        if HAS_NUMPY:
            import numpy as _np
            points = [_coerce_point(x) for x in _np.linspace(start, end, steps).tolist()]
        else:
            points = [_coerce_point(start + (end - start) * i / (steps - 1)) for i in range(steps)]
    else:
        return None, (
            f"sweep['{var_name}'] must be a list of values or "
            f"a dict with 'start', 'end', 'steps'"
        )

    base_vars = dict(variables or {})
    results = []
    for pt in points:
        step_vars = {**base_vars, var_name: pt}
        result, err = safe_eval_math(expr, step_vars)
        if err:
            return None, f"Error at {var_name}={pt}: {err}"
        results.append(result)

    return results, None
