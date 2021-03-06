import taichi as ti

@ti.all_archs
def test_1d():
  N = 16

  x = ti.var(ti.f32, shape=(N,))
  y = ti.var(ti.f32, shape=(N,))

  @ti.kernel
  def func():
    for i in range(N):
      y[i] = x[i]

  for i in range(N):
    x[i] = i * 2

  func()

  for i in range(N):
    assert y[i] == i * 2

@ti.all_archs
def test_3d():
  N = 2
  M = 2

  x = ti.var(ti.f32, shape=(N, M))
  y = ti.var(ti.f32, shape=(N, M))

  @ti.kernel
  def func():
    for I in ti.grouped(x):
        y[I] = x[I]

  for i in range(N):
    for j in range(M):
      x[i, j] = i * 10 + j

  func()

  for i in range(N):
    for j in range(M):
      assert y[i, j] == i * 10 + j
