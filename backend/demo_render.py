import subprocess, os, secrets, shutil
from pathlib import Path

ffmpeg = r'C:\src\pics\tools\ffmpeg\ffmpeg.exe'
ffprobe = r'C:\src\pics\tools\ffmpeg\ffprobe.exe'
w, h = 1920, 1080
tmp = Path(r'G:\photoide\slideshows\demo_tmp')
if tmp.exists():
    shutil.rmtree(tmp)
tmp.mkdir(parents=True, exist_ok=True)

slug = secrets.token_urlsafe(16)
out_dir = Path(r'G:\photoide\slideshows') / slug
out_dir.mkdir(parents=True, exist_ok=True)
out = str(out_dir / 'slideshow.mp4')

album_name = "Viagem para Maceio julho 2026"

items = [
    ('image', 90,  r'G:\photoide\organized\2026_07\20260727_175533(1).jpg', 4.0),
    ('image', 270, r'G:\photoide\organized\2026_07\20260727_222532.jpg', 4.0),
    ('video', 270, r'G:\photoide\transcoded_videos\193619_20260728_174751_transcoded.mp4', None),
    ('video', 90,  r'G:\photoide\transcoded_videos\193615_20260728_174320_transcoded.mp4', None),
]

def blur_bg(rot):
    r = {90: 'transpose=1,', 270: 'transpose=2,', 180: 'hflip,vflip,'}.get(rot, '')
    fg = f'{r}scale={w}:{h}:force_original_aspect_ratio=decrease,setsar=1'
    bg = f'{r}scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=20:20,eq=brightness=-0.2'
    return f'[0:v]split=2[s1][s2];[s1]{bg}[bg];[s2]{fg}[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=24[out]'

def run(cmd, label):
    print(f'  [{label}]...')
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print(f'  ERRO: {r.stderr[-800:]}')
        return False
    return True

def probe_duration(path):
    r = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1', path],
                       capture_output=True, text=True, timeout=10)
    try:
        return max(0.5, float(r.stdout.strip()))
    except Exception:
        return 8.0

def probe_has_audio(path):
    r = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'a',
                        '-show_entries', 'stream=codec_type',
                        '-of', 'default=noprint_wrappers=1', path],
                       capture_output=True, text=True, timeout=10)
    return 'audio' in r.stdout

clips = []
intro_src = None
outro_src = None

for i, (mtype, rot, src, dur) in enumerate(items):
    clip = str(tmp / f'clip_{i}.mp4')
    fc = blur_bg(rot)
    print(f'  src: {Path(src).name}')
    if mtype == 'image':
        if intro_src is None:
            intro_src = src
        outro_src = src
        ok = run([ffmpeg, '-y', '-loop', '1', '-t', str(dur), '-noautorotate', '-i', src,
                  '-f', 'lavfi', '-t', str(dur), '-i', 'aevalsrc=0:c=stereo:s=44100',
                  '-filter_complex', fc, '-map', '[out]', '-map', '1:a',
                  '-c:v', 'h264_qsv', '-global_quality', '26',
                  '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-shortest', clip],
                 f'Clip {i} imagem rot={rot}')
    else:
        has_a = probe_has_audio(src)
        vid_dur = probe_duration(src)
        if has_a:
            ok = run([ffmpeg, '-y', '-noautorotate', '-i', src,
                      '-filter_complex', fc, '-map', '[out]', '-map', '0:a',
                      '-c:v', 'h264_qsv', '-global_quality', '26',
                      '-c:a', 'aac', '-ar', '44100', '-ac', '2', clip],
                     f'Clip {i} video c/audio')
        else:
            ok = run([ffmpeg, '-y', '-noautorotate', '-i', src,
                      '-f', 'lavfi', '-t', str(vid_dur), '-i', 'aevalsrc=0:c=stereo:s=44100',
                      '-filter_complex', fc, '-map', '[out]', '-map', '1:a',
                      '-c:v', 'h264_qsv', '-global_quality', '26',
                      '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-shortest', clip],
                     f'Clip {i} video sem audio')
    if ok:
        clips.append(clip)
        print(f'  => clip_{i}.mp4 OK')

# Intro
intro_clip = str(tmp / 'clip_intro.mp4')
intro_dur = 6.0
safe_album = album_name.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
fade_expr = "if(lt(t\\,0.8)\\,t/0.8\\,if(gt(t\\,5.2)\\,(6.0-t)/0.8\\,1))"

FONTFILE = r"'C\:/Windows/Fonts/arial.ttf'"
FONTFILE_B = r"'C\:/Windows/Fonts/arialbd.ttf'"

import datetime as _dt
n_photos = sum(1 for t, *_ in items if t == 'image')
n_videos = sum(1 for t, *_ in items if t == 'video')
total_dur_s = sum(d or 0 for _, _, _, d in items if d)
dur_str = f"{int(total_dur_s//60)}min {int(total_dur_s%60):02d}s" if total_dur_s >= 60 else f"{int(total_dur_s)}s"
now_str = _dt.datetime.now().strftime("%d/%m/%Y")
def _e(s): return s.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
line2 = _e(f"{now_str}  |  {dur_str}")
line3 = _e(f"{n_photos} foto{'s' if n_photos != 1 else ''}  •  {n_videos} video{'s' if n_videos != 1 else ''}")

if intro_src:
    cx = "(w-text_w)/2"
    intro_bg = (
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},boxblur=25:25,eq=brightness=-0.5[bg];"
        f"[bg]drawtext=fontfile={FONTFILE_B}:text='{safe_album}':fontcolor=white:fontsize=68:"
        f"x={cx}:y=(h-text_h)/2-60:shadowcolor=black:shadowx=2:shadowy=2:alpha='{fade_expr}'[t1];"
        f"[t1]drawtext=fontfile={FONTFILE}:text='{line2}':fontcolor=0xDDDDDD:fontsize=36:"
        f"x={cx}:y=(h-text_h)/2+20:shadowcolor=black:shadowx=1:shadowy=1:alpha='{fade_expr}'[t2];"
        f"[t2]drawtext=fontfile={FONTFILE}:text='{line3}':fontcolor=0xAAAAAA:fontsize=30:"
        f"x={cx}:y=(h-text_h)/2+70:shadowcolor=black:shadowx=1:shadowy=1:alpha='{fade_expr}'[out]"
    )
    ok = run([ffmpeg, '-y', '-loop', '1', '-t', str(intro_dur), '-noautorotate', '-i', intro_src,
              '-f', 'lavfi', '-t', str(intro_dur), '-i', 'aevalsrc=0:c=stereo:s=44100',
              '-filter_complex', intro_bg,
              '-map', '[out]', '-map', '1:a',
              '-c:v', 'h264_qsv', '-global_quality', '26',
              '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-shortest', intro_clip],
             'Intro')
    if not ok:
        run([ffmpeg, '-y',
             '-f', 'lavfi', '-t', str(intro_dur), '-i', f'color=black:s={w}x{h}:r=24',
             '-f', 'lavfi', '-t', str(intro_dur), '-i', 'aevalsrc=0:c=stereo:s=44100',
             '-vf', f"drawtext=text='{safe_album}':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2",
             '-c:v', 'h264_qsv', '-global_quality', '26',
             '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-shortest', intro_clip],
            'Intro fallback preto')

# Outro
outro_clip = str(tmp / 'clip_outro.mp4')
outro_dur = 4.0
outro_src = outro_src or intro_src

if outro_src:
    outro_bg = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},boxblur=25:25,eq=brightness=-0.5[bg];"
                f"[bg]drawtext=fontfile={FONTFILE}:text='The End':fontcolor=white:fontsize=96:"
                f"x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=3:shadowy=3[out]")
    ok = run([ffmpeg, '-y', '-loop', '1', '-t', str(outro_dur), '-noautorotate', '-i', outro_src,
              '-f', 'lavfi', '-t', str(outro_dur), '-i', 'aevalsrc=0:c=stereo:s=44100',
              '-filter_complex', outro_bg,
              '-map', '[out]', '-map', '1:a',
              '-c:v', 'h264_qsv', '-global_quality', '26',
              '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-shortest', outro_clip],
             'Outro')
    if not ok:
        run([ffmpeg, '-y',
             '-f', 'lavfi', '-t', str(outro_dur), '-i', f'color=black:s={w}x{h}:r=24',
             '-f', 'lavfi', '-t', str(outro_dur), '-i', 'aevalsrc=0:c=stereo:s=44100',
             '-vf', "drawtext=text='The End':fontcolor=white:fontsize=96:x=(w-text_w)/2:y=(h-text_h)/2",
             '-c:v', 'h264_qsv', '-global_quality', '26',
             '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-shortest', outro_clip],
            'Outro fallback preto')

# Crossfade entre clips via xfade (apenas entre clipes >= 10s)
all_clips = [intro_clip] + clips + [outro_clip]
XF_DUR = 1.0
SHORT_THRESH = 10.0  # clipes mais curtos que isso nao recebem transicao

clip_durs = [probe_duration(c) for c in all_clips]

print('Concatenando com crossfade...')
if len(all_clips) == 1:
    import shutil; shutil.copy2(all_clips[0], out)
else:
    inputs = []
    for c in all_clips:
        inputs += ['-i', c]

    n = len(all_clips)
    # Monta cadeia xfade: so aplica transicao onde AMBOS os clips adjacentes >= SHORT_THRESH
    # Rastreia offset acumulado no stream de video resultante
    vid_label = '0:v'  # label atual do video
    xf_count = 0
    fc_video = []
    acc_offset = 0.0  # offset acumulado no tempo do stream de saida
    xf_applied = []  # (idx_a, idx_b, xf_dur) para calcular offset de audio

    for idx in range(1, n):
        prev_dur = clip_durs[idx - 1]
        cur_dur = clip_durs[idx]
        can_xf = prev_dur >= SHORT_THRESH and cur_dur >= SHORT_THRESH
        xf_dur = min(XF_DUR, prev_dur / 2 - 0.05, cur_dur / 2 - 0.05) if can_xf else 0.0
        xf_dur = max(xf_dur, 0.0)

        if xf_dur > 0:
            offset = acc_offset + prev_dur - xf_dur
            out_label = f'v{xf_count + 1}'
            fc_video.append(f'[{vid_label}][{idx}:v]xfade=transition=fade:duration={xf_dur:.3f}:offset={offset:.3f}[{out_label}]')
            xf_applied.append(xf_dur)
            vid_label = out_label
            xf_count += 1
            acc_offset += prev_dur - xf_dur
        else:
            xf_applied.append(0.0)
            acc_offset += prev_dur

    # Normaliza fps, pix_fmt e SAR antes do concat/xfade
    norm_parts = []
    for i in range(n):
        norm_parts.append(f'[{i}:v]fps=24,format=yuv420p,setsar=1[nv{i}]')
        norm_parts.append(f'[{i}:a]aresample=44100[na{i}]')

    audio_in = ''.join(f'[na{i}]' for i in range(n))
    if xf_count == 0:
        # Sem nenhum xfade: usa concat simples
        vid_in = ''.join(f'[nv{i}]' for i in range(n))
        fc = (';'.join(norm_parts) +
              f';{vid_in}concat=n={n}:v=1:a=0[vout]' +
              f';{audio_in}concat=n={n}:v=0:a=1[aout]')
    else:
        # Refaz cadeia xfade com labels normalizados
        vid_label2 = 'nv0'
        xf_count2 = 0
        fc_video2 = []
        acc_offset2 = 0.0
        for idx in range(1, n):
            prev_dur = clip_durs[idx - 1]
            cur_dur = clip_durs[idx]
            can_xf = prev_dur >= SHORT_THRESH and cur_dur >= SHORT_THRESH
            xf_dur2 = min(XF_DUR, prev_dur / 2 - 0.05, cur_dur / 2 - 0.05) if can_xf else 0.0
            if xf_dur2 > 0:
                offset2 = acc_offset2 + prev_dur - xf_dur2
                out_label2 = f'xv{xf_count2 + 1}'
                fc_video2.append(f'[{vid_label2}][nv{idx}]xfade=transition=fade:duration={xf_dur2:.3f}:offset={offset2:.3f}[{out_label2}]')
                vid_label2 = out_label2
                xf_count2 += 1
                acc_offset2 += prev_dur - xf_dur2
            else:
                acc_offset2 += prev_dur
        fc_video2.append(f'[{vid_label2}][vout]')
        fc_video2.append(f'{audio_in}concat=n={n}:v=0:a=1[aout]')
        fc = ';'.join(norm_parts) + ';' + ';'.join(fc_video2)

    r = subprocess.run(
        [ffmpeg, '-y'] + inputs + [
            '-filter_complex', fc,
            '-map', '[vout]', '-map', '[aout]',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-ar', '44100', '-ac', '2',
            '-movflags', '+faststart', out,
        ],
        capture_output=True, text=True, timeout=300
    )
    if r.returncode != 0:
        print('ERRO xfade:', r.stderr[-800:])
        import sys; sys.exit(1)

print('Tamanho:', round(os.path.getsize(out) / 1024 / 1024, 1), 'MB')

import sys
sys.path.insert(0, str(Path(__file__).parent))
from app.core.database import SessionLocal
from app.models.models import SlideshowRenderJob

db = SessionLocal()
job = SlideshowRenderJob(
    slug=slug,
    album_id=2,
    status='done',
    output_path=out,
    params={'album_name': album_name, 'resolution': f'{w}x{h}'}
)
db.add(job)
db.commit()
db.close()
print(f'URL: https://myrtille.pics.casa/s/{slug}')
