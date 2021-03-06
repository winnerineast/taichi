import taichi as ti

@ti.all_archs
def test_linear():
  x = ti.var(ti.i32)
  y = ti.var(ti.i32)

  n = 128

  @ti.layout
  def place():
    ti.root.dense(ti.i, n).place(x)
    ti.root.dense(ti.i, n).place(y)

  @ti.kernel
  def fill():
    for i in x:
      x[i] = i
      y[i] = i * 2
      
  fill()

  for i in range(n):
    assert x[i] == i
    assert y[i] == i * 2
    
    
@ti.all_archs
def test_nested():
  x = ti.var(ti.i32)
  y = ti.var(ti.i32)
  
  n = 128
  
  @ti.layout
  def place():
    ti.root.dense(ti.i, n // 4).dense(ti.i, 4).place(x)
    ti.root.dense(ti.i, n).place(y)
  
  @ti.kernel
  def fill():
    for i in x:
      x[i] = i
      y[i] = i * 2
  
  fill()
  
  for i in range(n):
    assert x[i] == i
    assert y[i] == i * 2

@ti.all_archs
def test_nested2():
  x = ti.var(ti.i32)
  y = ti.var(ti.i32)
  
  n = 2048
  
  @ti.layout
  def place():
    ti.root.dense(ti.i, n // 512).dense(ti.i, 16).dense(ti.i, 8).dense(ti.i, 4).place(x)
    ti.root.dense(ti.i, n).place(y)
  
  @ti.kernel
  def fill():
    for i in x:
      x[i] = i
      y[i] = i * 2
  
  fill()
  
  for i in range(n):
    assert x[i] == i
    assert y[i] == i * 2
    
@ti.all_archs
def test_nested_2d():
  x = ti.var(ti.i32)
  y = ti.var(ti.i32)
  
  n = 32
  
  @ti.layout
  def place():
    ti.root.dense(ti.ij, n // 4).dense(ti.ij, 4).place(x, y)
  
  @ti.kernel
  def fill():
    for i, j in x:
      x[i, j] = i + j * 2
  
  fill()
  
  for i in range(n):
    for j in range(n):
      assert x[i, j] == i + j * 2
      
@ti.all_archs
def test_nested_2d_more_nests():
  x = ti.var(ti.i32)
  y = ti.var(ti.i32)
  
  n = 64
  
  @ti.layout
  def place():
    ti.root.dense(ti.ij, n // 16).dense(ti.ij, 2).dense(ti.ij, 4).dense(ti.ij, 2).place(x, y)
  
  @ti.kernel
  def fill():
    for i, j in x:
      x[i, j] = i + j * 2
  
  fill()
  
  for i in range(n):
    for j in range(n):
      assert x[i, j] == i + j * 2
    
@ti.all_archs
def test_linear_k():
  x = ti.var(ti.i32)
  
  n = 128
  
  @ti.layout
  def place():
    ti.root.dense(ti.k, n).place(x)
  
  @ti.kernel
  def fill():
    for i in x:
      x[i] = i
      
  fill()
  
  for i in range(n):
    assert x[i] == i

