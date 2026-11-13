"""Interactive 3D playback of the ramp run in a desktop window.

    python3 viewer.py            # uses whatever has been synced (run `sh sync_results.sh` first for the latest)
    python3 viewer.py --sync     # sync from the server first

Controls: mouse rotate (left drag) / pan (shift+drag) / zoom (scroll), at any time, also while playing.
    space  play / pause          left/right arrows  step one frame
    slider scrub in time         r  reset camera to the side view
Frames are cached after first load, so the second pass plays smoothly.
"""
import subprocess, sys
import pyvista as pv
import cfdviz

if '--sync' in sys.argv:
    subprocess.run(['sh', 'sync_results.sh'], cwd=cfdviz.HERE, check=True)

FR = cfdviz.frames()
label = cfdviz.Labeller()
cache = {}
state = dict(i=len(FR) - 1, playing=False)
P_MAX = 6.0   # kPa, fixed colour scale so frames are comparable


def get(i):
    if i not in cache:
        cache[i] = cfdviz.load_frame(FR[i])
    return cache[i]


p = pv.Plotter(window_size=(1400, 820), title='v6 hull — CFD ramp to 20 mph', off_screen='--test' in sys.argv)


def show(i):
    state['i'] = i
    hull, fs = get(i)
    p.add_mesh(fs, name='water', scalars='elevation_mm', cmap='RdBu_r', clim=(-60, 60), opacity=0.85,
               scalar_bar_args=dict(title='water surface (mm)', position_x=0.05, position_y=0.05, width=0.3))
    p.add_mesh(hull, name='hull', scalars='pressure_kPa', cmap='viridis', clim=(0, P_MAX),
               scalar_bar_args=dict(title='hull pressure (kPa)', position_x=0.62, position_y=0.05, width=0.3))
    p.add_text(label(FR[i]) + ('' if not state['playing'] else '   ▶'), name='label', font_size=12)
    p.render()


def on_slider(value):
    i = int(round(value))
    if i != state['i']:
        show(i)


slider = p.add_slider_widget(on_slider, [0, len(FR) - 1], value=state['i'], title='frame (0.05 s apart)',
                             pointa=(0.3, 0.92), pointb=(0.95, 0.92), style='modern', fmt='%.0f')


def step(k):
    i = (state['i'] + k) % len(FR)
    slider.GetRepresentation().SetValue(i)
    show(i)


def toggle():
    state['playing'] = not state['playing']
    show(state['i'])


def tick(_step):
    if state['playing']:
        step(1)


p.add_key_event('space', toggle)
p.add_key_event('Right', lambda: step(1))
p.add_key_event('Left', lambda: step(-1))
p.add_key_event('r', lambda: (setattr(p, 'camera_position', cfdviz.SIDE_VIEW), p.render()))

show(state['i'])
p.camera_position = cfdviz.SIDE_VIEW

if '--test' in sys.argv:          # headless check: render first and last frame to PNGs
    for i in (0, len(FR) - 1):
        show(i); p.screenshot(str(cfdviz.CASE / f'viewer-test-{i}.png'))
    print('rendered', len(FR), 'frames available')
    sys.exit(0)

p.add_timer_event(max_steps=10**9, duration=100, callback=tick)   # ~10 frames/s when playing
print(f'{len(FR)} frames, t = {FR[0].name} … {FR[-1].name} s.  Space = play/pause, arrows = step, r = reset view.')
p.show()
