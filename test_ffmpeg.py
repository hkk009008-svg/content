import subprocess
topic = "Empty space: the universes secret"
cmd1 = [
    'ffmpeg', '-f', 'lavfi', '-i', 'color=c=black:s=1280x720', '-vframes', '1',
    '-vf', f"drawtext=text='{topic}':fontcolor=white",
    '-y', 'test_out1.jpg'
]
res1 = subprocess.run(cmd1, capture_output=True, text=True)
print('Test 1 (no escape):', 'SUCCESS' if res1.returncode == 0 else 'FAIL', res1.stderr[-200:])

cmd2 = [
    'ffmpeg', '-f', 'lavfi', '-i', 'color=c=black:s=1280x720', '-vframes', '1',
    '-vf', f"drawtext=text='{topic.replace(':', '\\\\:')}':fontcolor=white",
    '-y', 'test_out2.jpg'
]
res2 = subprocess.run(cmd2, capture_output=True, text=True)
print('Test 2 (escaped):', 'SUCCESS' if res2.returncode == 0 else 'FAIL', res2.stderr[-200:])
