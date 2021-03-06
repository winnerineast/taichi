import inspect
from .core import taichi_lang_core
from .expr import Expr
from .snode import SNode
from .util import *
import numpy as np


def expr_init(rhs):
  if rhs is None:
    return Expr(taichi_lang_core.expr_alloca())
  if is_taichi_class(rhs):
    return rhs.variable()
  else:
    if isinstance(rhs, list):
      return [expr_init(e) for e in rhs]
    elif isinstance(rhs, tuple):
      return tuple(expr_init(e) for e in rhs)
    else:
      return Expr(taichi_lang_core.expr_var(Expr(rhs).ptr))


def wrap_scalar(x):
  if type(x) in [int, float]:
    return Expr(x)
  else:
    return x

def atomic_add(a, b):
  a.atomic_add(wrap_scalar(b))


def subscript(value, *indices):
  import numpy as np
  if isinstance(value, np.ndarray):
    return value.__getitem__(*indices)

  if isinstance(value, tuple) or isinstance(value, list):
    assert len(indices) == 1
    return value[indices[0]]

  if len(indices) == 1 and is_taichi_class(indices[0]):
    indices = indices[0].entries
  if is_taichi_class(value):
    return value.subscript(*indices)
  else:
    if isinstance(indices, tuple) and len(indices) == 1 and indices[0] is None:
      indices_expr_group = make_expr_group()
    else:
      indices_expr_group = make_expr_group(*indices)
    assert int(value.ptr.get_attribute("dim")) == indices_expr_group.size()
    return Expr(taichi_lang_core.subscript(value.ptr, indices_expr_group))


class PyTaichi:
  def __init__(self, kernels=[]):
    self.materialized = False
    self.prog = None
    self.layout_functions = []
    self.compiled_functions = {}
    self.compiled_grad_functions = {}
    self.scope_stack = []
    self.inside_kernel = False
    self.global_vars = []
    self.print_preprocessed = False
    self.default_fp = f32
    self.default_ip = i32
    self.target_tape = None
    self.inside_complex_kernel = False
    self.kernels = kernels
    Expr.materialize_layout_callback = self.materialize
  
  def set_default_fp(self, fp):
    assert fp in [f32, f64]
    self.default_fp = fp
  
  def set_default_ip(self, ip):
    assert ip in [i32, i64]
    self.default_ip = ip
  
  def materialize(self):
    if self.materialized:
      return
    Expr.layout_materialized = True
    self.prog = taichi_lang_core.Program()
    
    def layout():
      for func in self.layout_functions:
        func()
    
    print("Materializing layout...".format())
    taichi_lang_core.layout(layout)
    self.materialized = True
    for var in self.global_vars:
      assert var.ptr.snode() is not None, 'Some variable(s) not placed'
  
  def clear(self):
    if self.prog:
      self.prog.finalize()
      self.prog = None
    Expr.materialize_layout_callback = None
    Expr.layout_materialized = False
  
  def get_tape(self, loss=None):
    from .tape import Tape
    return Tape(self, loss)
  
  def sync(self):
    self.prog.synchronize()


pytaichi = PyTaichi()

def get_runtime():
  return pytaichi

def make_constant_expr(val):
  if isinstance(val, int):
    if pytaichi.default_ip == i32:
      return Expr(taichi_lang_core.make_const_expr_i32(val))
    elif pytaichi.default_ip == i64:
      return Expr(taichi_lang_core.make_const_expr_i64(val))
    else:
      assert False
  else:
    if pytaichi.default_fp == f32:
      return Expr(taichi_lang_core.make_const_expr_f32(val))
    elif pytaichi.default_fp == f64:
      return Expr(taichi_lang_core.make_const_expr_f64(val))
    else:
      assert False


def reset():
  global pytaichi
  global root
  old_kernels = pytaichi.kernels
  pytaichi.clear()
  pytaichi = PyTaichi(old_kernels)
  for k in old_kernels:
    k.reset()
  taichi_lang_core.reset_default_compile_config()
  root = SNode(taichi_lang_core.get_root())


def inside_kernel():
  return pytaichi.inside_kernel

def index_nd(dim):
  return indices(*range(dim))

def global_var(dt, shape=None, needs_grad=False):

  # primal
  x = Expr(taichi_lang_core.make_id_expr(""))
  x.ptr = taichi_lang_core.global_new(x.ptr, dt)
  x.ptr.set_is_primal(True)
  pytaichi.global_vars.append(x)
  
  if taichi_lang_core.needs_grad(dt):
    # adjoint
    x_grad = Expr(taichi_lang_core.make_id_expr(""))
    x_grad.ptr = taichi_lang_core.global_new(x_grad.ptr, dt)
    x_grad.ptr.set_is_primal(False)
    x.set_grad(x_grad)

  if shape is not None:
    @layout
    def place():
      import taichi as ti
      dim = len(shape)
      ti.root.dense(index_nd(dim), shape).place(x)
      if needs_grad:
        ti.root.dense(index_nd(dim), shape).place(x.grad)

  return x


var = global_var

root = SNode(taichi_lang_core.get_root())


def layout(func):
  assert not pytaichi.materialized, "All layout must be specified before the first kernel launch / data access."
  pytaichi.layout_functions.append(func)


def ti_print(var):
  code = inspect.getframeinfo(inspect.currentframe().f_back).code_context[0]
  arg_name = code[code.index('(') + 1: code.index(')')]
  taichi_lang_core.print_(Expr(var).ptr, arg_name)


def ti_int(var):
  if hasattr(var, '__ti_int__'):
    return var.__ti_int__()
  else:
    return int(var)


def ti_float(var):
  if hasattr(var, '__ti_float__'):
    return var.__ti_int__()
  else:
    return float(var)


def indices(*x):
  return [taichi_lang_core.Index(i) for i in x]


index = indices


def static(x):
  assert get_runtime().inside_kernel, 'ti.static can only be used inside Taichi kernels'
  assert isinstance(x, (bool, int, float, range, list, tuple)), 'Input to ti.static must have compile-time constant values, instead of {}'.format(type(x))
  return x

def grouped(x):
  assert get_runtime().inside_kernel, 'ti.grouped can only be used inside Taichi kernels'
  return x


def stop_grad(x):
  taichi_lang_core.stop_grad(x.snode().ptr)


def current_cfg():
  return taichi_lang_core.current_compile_config()


def default_cfg():
  return taichi_lang_core.default_compile_config()

from .kernel import *
from .ops import *
from .kernel_arguments import *
