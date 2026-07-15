from pathlib import Path
p = Path(r'G:\photoide\organized\2026_05\20260521_074935.jpg')
print('path', p)
print('exists', p.exists())
try:
    with p.open('rb') as f:
        data = f.read(1024)
    print('read bytes', len(data))
except Exception as e:
    print('OPEN ERR', type(e).__name__, e)
