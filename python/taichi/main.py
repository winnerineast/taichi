import sys
import os
import shutil
import time
import random
from taichi.tools.video import make_video, interpolate_frames

def test_python():
  print("\nRunning python tests...\n")
  import taichi as ti
  import pytest
  if ti.is_release():
    return int(pytest.main([os.path.join(ti.package_root(), 'tests')]))
  else:
    return int(pytest.main([os.path.join(ti.get_repo_directory(), 'tests')]))

def test_cpp():
  import taichi as ti
  if not ti.core.with_cuda():
    print("Skipping legacy tests (no GPU support)")
    return 0
  # Cpp tests use the legacy non LLVM backend
  os.environ['TI_LLVM'] = '0'
  ti.reset()
  print("Running C++ tests...")
  task = ti.Task('test')
  return task.run(*sys.argv[2:])

def main(debug=False):
  lines = []
  print()
  lines.append(u' *******************************************')
  lines.append(u' **                Taichi                 **')
  lines.append(u' **                                       **')
  lines.append(u' ** High-Performance Programming Language **')
  lines.append(u' *******************************************')
  print(u'\n'.join(lines))
  print()
  import taichi as ti

  ti.tc_core.set_core_debug(debug)

  argc = len(sys.argv)
  if argc == 1 or sys.argv[1] == 'help':
    print(
      "    Usage: ti run [task name]        |-> Run a specific task\n"
      "           ti test                   |-> Run all tests\n"
      "           ti test_python            |-> Run python tests\n"
      "           ti test_cpp               |-> Run cpp tests\n"
      "           ti build                  |-> Build C++ files\n"
      "           ti video                  |-> Make a video using *.png files in the current folder\n"
      "           ti doc                    |-> Build documentation\n"
      "           ti debug [script.py]      |-> Debug script\n")
    exit(-1)
  mode = sys.argv[1]

  t = time.time()
  if mode.endswith('.py'):
    with open(mode) as script:
      script = script.read()
    exec(script, {'__name__': '__main__'})
  elif mode.endswith('.cpp'):
    command = 'g++ {} -o {} -g -std=c++14 -O3 -lX11 -lpthread'.format(mode, mode[:-4])
    print(command)
    ret = os.system(command)
    if ret == 0:
      os.system('./{}'.format(mode[:-4]))
  elif mode == "run":
    if argc <= 2:
      print("Please specify [task name], e.g. test_math")
      exit(-1)
    name = sys.argv[2]
    task = ti.Task(name)
    task.run(*sys.argv[3:])
  elif mode == "debug":
    ti.core.set_core_trigger_gdb_when_crash(True)
    if argc <= 2:
      print("Please specify [file name], e.g. render.py")
      exit(-1)
    name = sys.argv[2]
    with open(name) as script:
      script = script.read()
    exec(script, {'__name__': '__main__'})
  elif mode == "test_python":
    return test_python()
  elif mode == "test_cpp":
    return test_cpp()
  elif mode == "test":
    if test_python() != 0:
      return -1
    return test_cpp()
  elif mode == "build":
    ti.core.build()
  elif mode == "format":
    ti.core.format()
  elif mode == "statement":
    exec(sys.argv[2])
  elif mode == "update":
    ti.core.update(True)
    ti.core.build()
  elif mode == "asm":
    fn = sys.argv[2]
    os.system(r"sed '/^\s*\.\(L[A-Z]\|[a-z]\)/ d' {0} > clean_{0}".format(fn))
  elif mode == "exec":
    import subprocess
    exec_name = sys.argv[2]
    folder = ti.get_bin_directory()
    assert exec_name in os.listdir(folder)
    subprocess.call([os.path.join(folder, exec_name)] + sys.argv[3:])
  elif mode == "interpolate":
    interpolate_frames('.')
  elif mode == "amal":
    cwd = os.getcwd()
    os.chdir(ti.get_repo_directory())
    with open('misc/amalgamate.py') as script:
      script = script.read()
    exec(script, {'__name__': '__main__'})
    os.chdir(cwd)
    shutil.copy(os.path.join(ti.get_repo_directory(), 'build/taichi.h'), './taichi.h')
  elif mode == "doc":
    os.system('cd docs && sphinx-build -b html . build')
  elif mode == "video":
    files = sorted(os.listdir('.'))
    files = list(filter(lambda x: x.endswith('.png'), files))
    if len(sys.argv) >= 3:
      frame_rate = int(sys.argv[2])
    else:
      frame_rate = 24
    if len(sys.argv) >= 4:
      trunc = int(sys.argv[3])
      files = files[:trunc]
    ti.info('Making video using {} png files...', len(files))
    ti.info("frame_rate={}", frame_rate)
    output_fn = 'video.mp4'
    make_video(files, output_path=output_fn, frame_rate=frame_rate)
    ti.info('Done! Output video file = {}', output_fn)
  elif mode == "convert":
    # http://www.commandlinefu.com/commands/view/3584/remove-color-codes-special-characters-with-sed
    # TODO: Windows support
    for fn in sys.argv[2:]:
      print("Converting logging file: {}".format(fn))
      tmp_fn = '/tmp/{}.{:05d}.backup'.format(fn, random.randint(0, 10000))
      shutil.move(fn, tmp_fn)
      command = r'sed -r "s/\x1B\[([0-9]{1,2}(;[0-9]{1,2})?)?[m|K]//g"'
      os.system('{} {} > {}'.format(command, tmp_fn, fn))
  elif mode == "merge":
    import cv2 # TODO: remove this dependency
    import numpy as np
    folders = sys.argv[2:]
    os.makedirs('merged', exist_ok=True)
    for fn in sorted(os.listdir(folders[0])):
      imgs = []
      for fld in folders:
        img = cv2.imread(os.path.join(fld, fn))
        imgs.append(img)
      img = np.hstack(imgs)
      cv2.imwrite(os.path.join('merged', fn), img)
  else:
    name = sys.argv[1]
    print('Running task [{}]...'.format(name))
    task = ti.Task(name)
    task.run(*sys.argv[2:])
  print()
  print(">>> Running time: {:.2f}s".format(time.time() - t))

if __name__ == '__main__':
  exit(main())
