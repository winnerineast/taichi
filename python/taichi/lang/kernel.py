import inspect
from .transformer import ASTTransformer
import ast
from .kernel_arguments import *
from .util import *

def remove_indent(lines):
  lines = lines.split('\n')
  to_remove = 0
  for i in range(len(lines[0])):
    if lines[0][i] == ' ':
      to_remove = i + 1
    else:
      break

  cleaned = []
  for l in lines:
    cleaned.append(l[to_remove:])
    if len(l) >= to_remove:
      for i in range(to_remove):
        assert l[i] == ' '

  return '\n'.join(cleaned)

# The ti.func decorator

def func(foo):
  from .impl import get_runtime
  src = remove_indent(inspect.getsource(foo))
  tree = ast.parse(src)
  
  func_body = tree.body[0]
  func_body.decorator_list = []
  
  visitor = ASTTransformer(transform_args=False)
  visitor.visit(tree)
  ast.fix_missing_locations(tree)
  
  if get_runtime().print_preprocessed:
    import astor
    print('After preprocessing:')
    print(astor.to_source(tree.body[0], indent_with='  '))
  
  ast.increment_lineno(tree, inspect.getsourcelines(foo)[1] - 1)
  
  frame = inspect.currentframe().f_back
  exec(compile(tree, filename=inspect.getsourcefile(foo), mode='exec'),
       dict(frame.f_globals, **frame.f_locals), locals())
  compiled = locals()[foo.__name__]
  return compiled


class KernelTemplateMapper:
  def __init__(self, annotations, template_slot_locations):
    self.annotations = annotations
    self.num_args = len(annotations)
    self.template_slot_locations = template_slot_locations
    self.mapping = {}

  def extract(self, args):
    extracted = []
    for i in range(self.num_args):
      if hasattr(self.annotations[i], 'extract'):
        extracted.append(self.annotations[i].extract(args[i]))
      else:
        extracted.append(None)
    return tuple(extracted)

  def lookup(self, args):
    if len(args) != self.num_args:
      raise Exception(f'{self.num_args} argument(s) needed but {len(args)} provided.')

    key = self.extract(args)
    if key not in self.mapping:
      count = len(self.mapping)
      self.mapping[key] = count
    return self.mapping[key]


class KernelDefError(Exception):
  def __init__(self, msg):
    super().__init__(msg)


class KernelArgError(Exception):
  def __init__(self, pos, needed, provided):
    self.pos = pos
    self.needed = needed
    self.provided = provided

  def message(self):
    return 'Argument {} (type={}) cannot be converted into required type {}'.format(
      self.pos,
      str(self.needed),
      str(self.provided))


class Kernel:
  def __init__(self, func, is_grad, classkernel=False):
    self.func = func
    self.is_grad = is_grad
    self.arguments = []
    self.argument_names = []
    self.classkernel = classkernel
    self.extract_arguments()
    self.template_slot_locations = []
    for i in range(len(self.arguments)):
      if isinstance(self.arguments[i], template):
        self.template_slot_locations.append(i)
    self.mapper = KernelTemplateMapper(self.arguments, self.template_slot_locations)
    from .impl import get_runtime
    get_runtime().kernels.append(self)
    self.reset()

  def reset(self):
    from .impl import get_runtime
    self.runtime = get_runtime()
    if self.is_grad:
      self.compiled_functions = self.runtime.compiled_functions
    else:
      self.compiled_functions = self.runtime.compiled_grad_functions

  def extract_arguments(self):
    sig = inspect.signature(self.func)
    params = sig.parameters
    arg_names = params.keys()
    for i, arg_name in enumerate(arg_names):
      param = params[arg_name]
      if param.kind == inspect.Parameter.VAR_KEYWORD:
        raise KernelDefError(
          'Taichi kernels do not support variable keyword parameters (i.e., **kwargs)')
      if param.kind == inspect.Parameter.VAR_POSITIONAL:
        raise KernelDefError(
          'Taichi kernels do not support variable positional parameters (i.e., *args)')
      if param.default is not inspect.Parameter.empty:
        raise KernelDefError(
          'Taichi kernels do not support default values for arguments')
      if param.kind == inspect.Parameter.KEYWORD_ONLY:
        raise KernelDefError('Taichi kernels do not support keyword parameters')
      if param.kind != inspect.Parameter.POSITIONAL_OR_KEYWORD:
        raise KernelDefError(
          'Taichi kernels only support "positional or keyword" parameters')
      annotation = param.annotation
      if param.annotation is inspect.Parameter.empty:
        if i == 0 and self.classkernel:
          annotation = template()
        else:
          raise KernelDefError('Taichi kernels parameters must be type annotated')
      self.arguments.append(annotation)
      self.argument_names.append(param.name)

  def materialize(self, key=None, args=None, arg_features=None):
    if key is None:
      key = (self.func, 0)
    if not self.runtime.materialized:
      self.runtime.materialize()
    if key in self.compiled_functions:
      return
    grad_suffix = ""
    if self.is_grad:
      grad_suffix = "_grad"
    kernel_name = "{}_{}_{}".format(self.func.__name__, key[1], grad_suffix)
    print("Compiling kernel {}...".format(kernel_name))

    src = remove_indent(inspect.getsource(self.func))
    tree = ast.parse(src)
    if self.runtime.print_preprocessed:
      import astor
      print('Before preprocessing:')
      print(astor.to_source(tree.body[0]))

    func_body = tree.body[0]
    func_body.decorator_list = []

    visitor = ASTTransformer(excluded_paremeters=self.template_slot_locations, func=self, arg_features=arg_features)

    visitor.visit(tree)
    ast.fix_missing_locations(tree)

    if self.runtime.print_preprocessed:
      import astor
      print('After preprocessing:')
      print(astor.to_source(tree.body[0], indent_with='  '))

    ast.increment_lineno(tree, inspect.getsourcelines(self.func)[1] - 1)

    # Discussions: https://github.com/yuanming-hu/taichi/issues/282
    import copy
    global_vars = copy.copy(self.func.__globals__)

    freevar_names = self.func.__code__.co_freevars
    closure = self.func.__closure__
    if closure:
      freevar_values = list(map(lambda x: x.cell_contents, closure))
      for name, value in zip(freevar_names, freevar_values):
        global_vars[name] = value

    # inject template parameters into globals
    for i in self.template_slot_locations:
      template_var_name = self.argument_names[i]
      global_vars[template_var_name] = args[i]


    local_vars = {}
    exec(compile(tree, filename=inspect.getsourcefile(self.func), mode='exec'),
         global_vars, local_vars)
    compiled = local_vars[self.func.__name__]

    taichi_kernel = taichi_lang_core.create_kernel(kernel_name, self.is_grad)

    # Do not change the name of 'taichi_ast_generator'
    # The warning system needs this identifier to remove unnecessary messages
    def taichi_ast_generator():
      self.runtime.inside_kernel = True
      compiled()
      self.runtime.inside_kernel = False

    taichi_kernel = taichi_kernel.define(taichi_ast_generator)

    assert key not in self.compiled_functions
    self.compiled_functions[key] = self.get_function_body(taichi_kernel)


  def get_function_body(self, t_kernel):
    # The actual function body
    def func__(*args):
      assert len(args) == len(
        self.arguments), '{} arguments needed but {} provided'.format(
        len(self.arguments), len(args))

      actual_argument_slot = 0
      for i, v in enumerate(args):
        needed = self.arguments[i]
        if isinstance(needed, template):
          continue
        provided = type(v)
        if isinstance(needed, taichi_lang_core.DataType) and needed in [f32, f64]:
          if type(v) not in [float, int]:
            raise KernelArgError(i, needed, provided)
          t_kernel.set_arg_float(actual_argument_slot, float(v))
        elif isinstance(needed, taichi_lang_core.DataType) and needed in [i32, i64]:
          if type(v) not in [int]:
            raise KernelArgError(i, needed, provided)
          t_kernel.set_arg_int(actual_argument_slot, int(v))
        elif isinstance(needed, np.ndarray) or needed == np.ndarray or (isinstance(v, np.ndarray) and isinstance(needed, ext_arr)):
          float32_types = [np.float32, np.int32, np.float64, np.int64]
          assert v.dtype in float32_types, 'Kernel arg supports float/int 32/64 np arrays only'
          tmp = np.ascontiguousarray(v)
          t_kernel.set_arg_nparray(actual_argument_slot, int(tmp.ctypes.data), tmp.nbytes)
          max_num_indices = taichi_lang_core.get_max_num_indices()
          assert len(tmp.shape) <= max_num_indices, "External array cannot have > {} indices".format(max_num_indices)
          for i, s in enumerate(tmp.shape):
            t_kernel.set_extra_arg_int(actual_argument_slot, i, s)
          # v[:] = tmp[:]
        else:
          has_torch = False
          try:
            import torch
            has_torch = True
          except:
            pass

          if has_torch and isinstance(v, torch.Tensor):
            tmp = v
            if str(v.device).startswith('cuda'):
              assert self.runtime.prog.config.arch == taichi_lang_core.Arch.gpu, 'Torch tensor on GPU yet taichi is on CPU'
            else:
              assert self.runtime.prog.config.arch == taichi_lang_core.Arch.x86_64, 'Torch tensor on CPU yet taichi is on GPU'
            t_kernel.set_arg_nparray(actual_argument_slot, int(tmp.data_ptr()),
                                     tmp.element_size() * tmp.nelement())
          else:
            assert False, 'Argument to kernels must have type float/int. If you are passing a PyTorch tensor, make sure it is on the same device (CPU/GPU) as taichi.'
        actual_argument_slot += 1
      if not self.classkernel and self.runtime.target_tape and not self.runtime.inside_complex_kernel:
        self.runtime.target_tape.insert(self, args)
      t_kernel()

    return func__


  def __call__(self, *args, **kwargs):
    assert len(kwargs) == 0, 'kwargs not supported for Taichi kernels'
    instance_id = self.mapper.lookup(args)
    key = (self.func, instance_id)
    self.materialize(key=key, args=args, arg_features=self.mapper.extract(args))
    return self.compiled_functions[key](*args)


def kernel(foo):
  ret = Kernel(foo, False)
  ret.grad = Kernel(foo, True)
  return ret


def classkernel(foo):
  primal = Kernel(foo, False, classkernel=True)
  adjoint = Kernel(foo, True, classkernel=True)

  def decorated(*args, __gradient=False, **kwargs):
    if __gradient:
      adjoint(*args, **kwargs)
    else:
      primal(*args, **kwargs)

    import taichi as ti
    runtime = ti.get_runtime()
    if runtime.target_tape and not runtime.inside_complex_kernel:
      runtime.target_tape.insert(decorated, args)

  return decorated
