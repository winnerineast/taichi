import taichi as ti

@ti.all_archs
def test_no_grad():
  x = ti.var(ti.f32)
  loss = ti.var(ti.f32)

  N = 1

  # no gradients allocated for x
  @ti.layout
  def place():
    ti.root.dense(ti.i, N).place(x)
    ti.root.place(loss, loss.grad)

  @ti.kernel
  def func():
    for i in range(N):
      ti.atomic_add(loss, x[i] ** 2)

  with ti.Tape(loss):
    func()
